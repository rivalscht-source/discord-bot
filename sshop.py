import discord
from discord.ext import commands
import json
import os
import asyncio
import random

# ================= [설정] =================
TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = 1568578268502818877

# 역할 ID
BUYER_ROLE_ID = 1568601475171491880
STAFF_ROLE_ID = 1568601515232243775

# ★ 티켓 열람 가능 역할 ID (3개)
TICKET_ACCESS_ROLE_IDS = [
    1568601469966356603,
    1568601471962849312,
    1568601467827265596
]

# 채널 ID
TICKET_CATEGORY_ID = 1568599884292038676  # 티켓 생성 카테고리
CHARGE_LOG_CHANNEL_ID = 1568958460442316860
STOCK_LOG_CHANNEL_ID = 1568599828882133073
LOG_CHANNEL_ID = 1568599842934329344
ADMIN_CHANNEL_ID = 1568881496473866303
SHOP_CHANNEL_ID = 1568599827003088929

BAN_CHANNEL_ID = 1568980439358640311      # 즉시 밴 채널
SUPPORT_TICKET_CHANNEL_ID = 1568599831625072730 # 문의 티켓 생성 채널

# ★ 승인 알림을 받을 관리자(본인) 디스코드 유저 ID
ADMIN_USER_ID = 1547892091370213476 

BANK_INFO = "토스뱅크 1002-4183-6438 (예금주: 최규현)"
DB_FILE = os.path.join(os.path.expanduser("~"), "shop_db.json")
# ========================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

db = {}

def load_db():
    global db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                if "coupons" not in db: db["coupons"] = {"WELCOME": 5000}
                if "categories" in db: del db["categories"]
                for uid in db["users"]:
                    if "total_spent" not in db["users"][uid]: db["users"][uid]["total_spent"] = 0
        except:
            db = {"products": {}, "users": {}, "used_coupons": {}, "coupons": {"WELCOME": 5000}}
            save_db()
    else:
        db = {"products": {}, "users": {}, "used_coupons": {}, "coupons": {"WELCOME": 5000}}
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"DB 저장 실패: {e}")

def get_user(user_id):
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0, "cart": [], "total_spent": 0}
        save_db()
    elif "total_spent" not in db["users"][uid]:
        db["users"][uid]["total_spent"] = 0
    return db["users"][uid]

# ----------------- [보안: 즉시 밴 시스템] -----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == BAN_CHANNEL_ID:
        if message.author.guild_permissions.administrator:
            pass
        else:
            try:
                await message.author.ban(reason="보안 채널 침입 (자동 밴)")
                print(f"[보안] {message.author.name} 님이 밴 처리됨.")
            except Exception as e:
                print(f"밴 실패: {e}")
        return

    await bot.process_commands(message)

# ----------------- [티켓 생성 UI (3초 에러 해결)] -----------------
class TicketCreateView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="📩 문의 티켓 생성", style=discord.ButtonStyle.primary, custom_id="create_support_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ★ 3초 제한 해결: 무조건 먼저 응답 (딜레이)
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        
        # 최대 3개 제한 확인
        user_tickets = [ch for ch in guild.text_channels if ch.name.startswith(f"문의-{interaction.user.name}")]
        if len(user_tickets) >= 3:
            return await interaction.followup.send(f"❌ 티켓은 최대 3개까지만 생성할 수 있습니다. 기존 티켓을 닫아주세요.", ephemeral=True)

        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role_id in TICKET_ACCESS_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 티켓 생성
        ticket_ch = await guild.create_text_channel(
            name=f"문의-{interaction.user.name}-{random.randint(1000, 9999)}", 
            category=category, 
            overwrites=overwrites
        )
        
        embed = discord.Embed(title="📩 1:1 문의 티켓", description="문의하실 내용을 이곳에 적어주세요. 스태프가 확인 후 답변드립니다.", color=0x3498db)
        embed.add_field(name="문의자", value=interaction.user.mention)
        
        mentions = interaction.user.mention
        for role_id in TICKET_ACCESS_ROLE_IDS:
            role = guild.get_role(role_id)
            if role: mentions += f" {role.mention}"
            
        await ticket_ch.send(embed=embed)
        await ticket_ch.send(mentions)
        
        await interaction.followup.send(f"✅ 문의 티켓이 생성되었습니다: {ticket_ch.mention}", ephemeral=True)

# ----------------- [UI: 관리자 모달 & 패널] -----------------
class AddProductModal(discord.ui.Modal, title="새 상품 등록"):
    item_name = discord.ui.TextInput(label="상품 이름", placeholder="예: 발로란트 계정", required=True, max_length=50)
    item_price = discord.ui.TextInput(label="상품 가격 (숫자만)", placeholder="예: 10000", required=True, max_length=10)
    item_desc = discord.ui.TextInput(label="상품 설명", style=discord.TextStyle.paragraph, required=True, max_length=200)
    item_title = discord.ui.TextInput(label="기본 DM 지급 문구", placeholder="예: 발로란트 계정 지급 완료!", required=True, max_length=100)
    item_data = discord.ui.TextInput(label="초기 지급 데이터 (줄바꿈)", style=discord.TextStyle.paragraph, placeholder="아이디: test1 / 비번: 1234\n아이디: test2 / 비번: 5678", required=False, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try: price = int(self.item_price.value)
        except ValueError: return await interaction.followup.send("❌ 가격은 숫자만 입력해주세요.", ephemeral=True)
        name = self.item_name.value
        
        initial_data = []
        if self.item_data.value:
            initial_data = [line.strip() for line in self.item_data.value.split('\n') if line.strip()]

        if name in db["products"]:
            db["products"][name]["price"] = price
            db["products"][name]["desc"] = self.item_desc.value
            db["products"][name]["delivery_titles"].append(self.item_title.value)
            db["products"][name]["delivery_data"].extend(initial_data)
            db["products"][name]["stock"] = len(db["products"][name]["delivery_data"])
        else:
            db["products"][name] = {
                "price": price, 
                "desc": self.item_desc.value, 
                "delivery_data": initial_data, 
                "delivery_titles": [self.item_title.value],
                "stock": len(initial_data)
            }
        save_db()
        
        stock_log = interaction.guild.get_channel(STOCK_LOG_CHANNEL_ID)
        if stock_log:
            embed = discord.Embed(title="📦 상품 등록/수정", color=0x3498db)
            embed.add_field(name="상품명", value=name, inline=True)
            embed.add_field(name="가격", value=f"{price}원", inline=True)
            embed.add_field(name="현재 재고", value=f"{db['products'][name]['stock']}개", inline=True)
            await stock_log.send(embed=embed)

        await interaction.followup.send(f"✅ **{name}** 상품 등록 완료! (현재 재고: {db['products'][name]['stock']}개)", ephemeral=True)

class AddCouponModal(discord.ui.Modal, title="새 쿠폰 생성"):
    coupon_code = discord.ui.TextInput(label="쿠폰 코드", placeholder="예: EVENT2026", required=True, max_length=20)
    coupon_amount = discord.ui.TextInput(label="충전 금액 (숫자만)", placeholder="예: 10000", required=True, max_length=10)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try: amount = int(self.coupon_amount.value)
        except ValueError: return await interaction.followup.send("❌ 금액은 숫자만 입력해주세요.", ephemeral=True)
        code = self.coupon_code.value.upper()
        if code in db["coupons"]: return await interaction.followup.send("❌ 이미 존재하는 쿠폰 코드입니다.", ephemeral=True)
        db["coupons"][code] = amount; save_db()
        await interaction.followup.send(f"✅ 쿠폰 **{code}** ({amount}원) 생성 완료.", ephemeral=True)

class AddStockModal(discord.ui.Modal, title="재고 데이터 추가 (최대 5개)"):
    def __init__(self, item_name):
        super().__init__()
        self.item_name = item_name
        
        self.d1 = discord.ui.TextInput(label="1번째 데이터 (필수)", placeholder="계정ID: test1 / 비번: 1234", required=True, max_length=200)
        self.d2 = discord.ui.TextInput(label="2번째 데이터 (선택)", placeholder="비워두면 등록 안 됨", required=False, max_length=200)
        self.d3 = discord.ui.TextInput(label="3번째 데이터 (선택)", placeholder="비워두면 등록 안 됨", required=False, max_length=200)
        self.d4 = discord.ui.TextInput(label="4번째 데이터 (선택)", placeholder="비워두면 등록 안 됨", required=False, max_length=200)
        self.d5 = discord.ui.TextInput(label="5번째 데이터 (선택)", placeholder="비워두면 등록 안 됨", required=False, max_length=200)
        
        self.add_item(self.d1)
        self.add_item(self.d2)
        self.add_item(self.d3)
        self.add_item(self.d4)
        self.add_item(self.d5)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        inputs = [self.d1.value, self.d2.value, self.d3.value, self.d4.value, self.d5.value]
        new_data = [val.strip() for val in inputs if val and val.strip()]
        
        if not new_data:
            return await interaction.followup.send("❌ 최소 1개의 데이터를 입력해야 합니다.", ephemeral=True)

        if self.item_name not in db["products"]: 
            return await interaction.followup.send("❌ 존재하지 않는 상품입니다.", ephemeral=True)

        db["products"][self.item_name]["delivery_data"].extend(new_data)
        db["products"][self.item_name]["stock"] = len(db["products"][self.item_name]["delivery_data"])
        save_db()

        stock_log = interaction.guild.get_channel(STOCK_LOG_CHANNEL_ID)
        if stock_log:
            embed = discord.Embed(title="🎁 재고 추가 입고", color=0x2ecc71)
            embed.add_field(name="상품명", value=self.item_name, inline=True)
            embed.add_field(name="추가된 수량", value=f"{len(new_data)}개", inline=True)
            embed.add_field(name="현재 총 재고", value=f"{db['products'][self.item_name]['stock']}개", inline=True)
            await stock_log.send(embed=embed)

        await interaction.followup.send(f"✅ **{self.item_name}**에 재고 **{len(new_data)}개**가 추가되었습니다. (현재 재고: {db['products'][self.item_name]['stock']}개)", ephemeral=True)

class AddDeliveryTitleModal(discord.ui.Modal, title="추가 지급 문구 등록"):
    def __init__(self, item_name):
        super().__init__()
        self.item_name = item_name
        self.title_input = discord.ui.TextInput(label=f"[{item_name}] 추가할 DM 제목", placeholder="예: A급 발로란트 계정 당첨!", required=True, max_length=100)
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        title = self.title_input.value.strip()
        if self.item_name not in db["products"]: return await interaction.followup.send("❌ 존재하지 않는 상품입니다.", ephemeral=True)

        if title in db["products"][self.item_name]["delivery_titles"]:
            return await interaction.followup.send("❌ 이미 등록된 문구입니다.", ephemeral=True)
            
        db["products"][self.item_name]["delivery_titles"].append(title)
        save_db()
        await interaction.followup.send(f"✅ **{self.item_name}**에 문구가 추가되었습니다. (총 {len(db['products'][self.item_name]['delivery_titles'])}개)", ephemeral=True)

class AdminPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ 상품 등록", style=discord.ButtonStyle.primary, custom_id="admin_add_product", row=0)
    async def add_product(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(AddProductModal())
    @discord.ui.button(label="🎟️ 쿠폰 생성", style=discord.ButtonStyle.success, custom_id="admin_add_coupon", row=0)
    async def add_coupon(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(AddCouponModal())
    
    @discord.ui.button(label="🎁 재고 추가 (최대 5개)", style=discord.ButtonStyle.success, custom_id="admin_add_stock", row=1)
    async def add_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not db["products"]: return await interaction.response.send_message("❌ 등록된 상품이 없습니다.", ephemeral=True)
        options = [discord.SelectOption(label=name, value=name, description=f"현재 재고: {data['stock']}개") for name, data in list(db["products"].items())[:25]]
        view = discord.ui.View(); select = discord.ui.Select(placeholder="재고를 추가할 상품 선택", options=options)
        async def select_callback(inter: discord.Interaction): 
            await inter.response.send_modal(AddStockModal(select.values[0]))
        select.callback = select_callback; view.add_item(select)
        await interaction.response.send_message("재고를 추가할 상품을 선택하세요:", view=view, ephemeral=True)

    @discord.ui.button(label="📝 지급 문구 추가", style=discord.ButtonStyle.secondary, custom_id="admin_add_title", row=1)
    async def add_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not db["products"]: return await interaction.response.send_message("❌ 등록된 상품이 없습니다.", ephemeral=True)
        options = [discord.SelectOption(label=name, value=name, description=f"문구 {len(data.get('delivery_titles', []))}개") for name, data in list(db["products"].items())[:25]]
        view = discord.ui.View(); select = discord.ui.Select(placeholder="문구를 추가할 상품 선택", options=options)
        async def select_callback(inter: discord.Interaction): await inter.response.send_modal(AddDeliveryTitleModal(select.values[0]))
        select.callback = select_callback; view.add_item(select)
        await interaction.response.send_message("지급 문구를 추가할 상품 선택:", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ 상품 삭제", style=discord.ButtonStyle.danger, custom_id="admin_del_product", row=2)
    async def del_product(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not db["products"]: return await interaction.response.send_message("❌ 상품 없음", ephemeral=True)
        options = [discord.SelectOption(label=name, value=name) for name in list(db["products"].keys())[:25]]
        view = discord.ui.View(); select = discord.ui.Select(placeholder="삭제할 상품 선택", options=options)
        async def select_callback(inter: discord.Interaction):
            del db["products"][select.values[0]]; save_db()
            await inter.response.send_message(f"🗑️ `{select.values[0]}` 삭제 완료.", ephemeral=True)
        select.callback = select_callback; view.add_item(select)
        await interaction.response.send_message("삭제할 상품 선택:", view=view, ephemeral=True)

# ----------------- [UI: 유저 상점 대시보드] -----------------
class ShopDashboardView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📦 제품 목록", style=discord.ButtonStyle.secondary, custom_id="shop_btn_products")
    async def products_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not db["products"]: return await interaction.response.send_message("❌ 등록된 상품이 없습니다.", ephemeral=True)
        embed = discord.Embed(title="📦 전체 제품 목록", color=0x2b2d31)
        val = ""
        for name, data in db["products"].items():
            val += f"**{name}** - {data['price']}원 (재고: {data['stock']}개)\n"
        embed.description = val
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @discord.ui.button(label="💳 충전", style=discord.ButtonStyle.primary, custom_id="shop_btn_charge")
    async def charge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="💳 충전 안내", description="충전 방식을 선택해주세요.\n\n🎟️ **쿠폰 사용**\n🏦 **계좌 이체**", color=0xfee75c)
        view = discord.ui.View()
        btn_coupon = discord.ui.Button(label="🎟️ 쿠폰 사용", style=discord.ButtonStyle.success, custom_id="use_coupon_btn"); btn_coupon.callback = self.use_coupon_callback
        btn_bank = discord.ui.Button(label="🏦 계좌 이체", style=discord.ButtonStyle.primary, custom_id="use_bank_btn"); btn_bank.callback = self.use_bank_callback
        view.add_item(btn_coupon); view.add_item(btn_bank)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    async def use_coupon_callback(self, interaction: discord.Interaction): await interaction.response.send_modal(CouponModal())
    async def use_bank_callback(self, interaction: discord.Interaction): await interaction.response.send_modal(BankTransferModal())
    
    @discord.ui.button(label="🛒 구매", style=discord.ButtonStyle.success, custom_id="shop_btn_buy")
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        select = ProductSelect()
        if not select.options or select.options[0].label == "상품 없음":
            return await interaction.response.send_message("❌ 구매 가능한 상품이 없습니다.", ephemeral=True)
        view.add_item(select)
        await interaction.response.send_message("구매할 상품을 선택하세요:", view=view, ephemeral=True)
        
    @discord.ui.button(label="🔄 새로고침", style=discord.ButtonStyle.primary, custom_id="shop_btn_refresh", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔄 상점 정보를 새로 불러왔습니다.", ephemeral=True)
    @discord.ui.button(label="👤 내 정보", style=discord.ButtonStyle.secondary, custom_id="shop_btn_myinfo", row=1)
    async def myinfo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        embed = discord.Embed(title=f"👤 {interaction.user.name} 님의 정보", color=0x3498db)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="💰 보유 금액 (잔액)", value=f"**{user.get('balance', 0):,}원**", inline=False)
        embed.add_field(name="💸 누적 결제 금액", value=f"**{user.get('total_spent', 0):,}원**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------- [모달: 쿠폰 및 계좌이체] -----------------
class CouponModal(discord.ui.Modal, title="쿠폰 사용"):
    code = discord.ui.TextInput(label="쿠폰 코드 입력", placeholder="예: WELCOME", required=True, max_length=20)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        code = self.code.value.upper(); uid = str(interaction.user.id)
        if code not in db.get("coupons", {}): return await interaction.followup.send("❌ 유효하지 않은 쿠폰입니다.", ephemeral=True)
        if uid in db["used_coupons"] and code in db["used_coupons"][uid]: return await interaction.followup.send("❌ 이미 사용한 쿠폰입니다.", ephemeral=True)
        
        amount = db["coupons"][code]; user = get_user(interaction.user.id); user["balance"] += amount
        if uid not in db["used_coupons"]: db["used_coupons"][uid] = []
        db["used_coupons"][uid].append(code); save_db()
        
        log_ch = interaction.guild.get_channel(CHARGE_LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="🎟️ 쿠폰 충전 완료", description=f"{interaction.user.mention} 님이 쿠폰을 사용하여 충전하셨습니다.", color=0x2ecc71)
            embed.add_field(name="충전 금액", value=f"{amount}원")
            embed.add_field(name="현재 잔액", value=f"{user['balance']}원")
            await log_ch.send(embed=embed)

        await interaction.followup.send(f"🎉 쿠폰 사용 완료! **{amount}원**이 충전되었습니다. (현재: {user['balance']}원)", ephemeral=True)

class BankTransferModal(discord.ui.Modal, title="계좌 이체 충전 신청"):
    deposit_name = discord.ui.TextInput(label="입금자명 (필수)", placeholder="실제 입금하신 분의 성함", required=True, max_length=20)
    amount = discord.ui.TextInput(label="입금 금액 (숫자만)", placeholder="예: 10000", required=True, max_length=10)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try: amt = int(self.amount.value)
        except ValueError: return await interaction.followup.send("❌ 금액은 숫자만 입력해주세요.", ephemeral=True)

        guild = interaction.guild; category = guild.get_channel(TICKET_CATEGORY_ID); staff_role = guild.get_role(STAFF_ROLE_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_ch = await guild.create_text_channel(name=f"충전-{interaction.user.name}-{random.randint(1000, 9999)}", category=category, overwrites=overwrites)
        
        embed = discord.Embed(title="🏦 계좌 이체 충전 대기", color=0xfee75c)
        embed.add_field(name="신청 유저", value=interaction.user.mention, inline=False)
        embed.add_field(name="입금자명", value=f"**{self.deposit_name.value}**", inline=False)
        embed.add_field(name="입금 금액", value=f"**{amt}원**", inline=False)
        embed.add_field(name="입금 계좌", value=f"`{BANK_INFO}`", inline=False)
        embed.set_footer(text="입금 확인 후, 관리자가 승인하면 자동 충전됩니다.")
        await ticket_ch.send(embed=embed)
        
        if staff_role: await ticket_ch.send(f"{interaction.user.mention} {staff_role.mention}")
        else: await ticket_ch.send(f"{interaction.user.mention}")
        
        try:
            admin_user = await bot.fetch_user(ADMIN_USER_ID)
            dm_embed = discord.Embed(title="🚨 계좌 이체 충전 승인 요청", description="새로운 충전 신청이 들어왔습니다.", color=0xe74c3c)
            dm_embed.add_field(name="신청 유저", value=interaction.user.mention, inline=False)
            dm_embed.add_field(name="입금자명", value=f"**{self.deposit_name.value}**", inline=False)
            dm_embed.add_field(name="금액", value=f"**{amt}원**", inline=False)
            dm_view = BankApproveView(user_id=interaction.user.id, amount=amt)
            await admin_user.send(embed=dm_embed, view=dm_view)
            await interaction.followup.send(f"✅ 충전 신청 완료. 티켓: {ticket_ch.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"✅ 충전 신청 완료. 티켓: {ticket_ch.mention}\n(⚠️ 관리자에게 DM을 보낼 수 없습니다. DM 차단을 해제해 주세요.)", ephemeral=True)

# ----------------- [UI: 계좌 충전 승인 버튼 (DM 전용)] -----------------
class BankApproveView(discord.ui.View):
    def __init__(self, user_id, amount):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount

    @discord.ui.button(label="✅ 입금 확인 및 충전 승인", style=discord.ButtonStyle.success, custom_id="bank_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_USER_ID:
            return await interaction.response.send_message("❌ 관리자만 승인할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=False)
            
        user = get_user(self.user_id)
        user["balance"] += self.amount
        save_db()

        embed = discord.Embed(title="✅ 충전 승인 완료", description=f"<@{self.user_id}> 님에게 **{self.amount}원**이 충전되었습니다.", color=0x2ecc71)
        embed.add_field(name="현재 잔액", value=f"{user['balance']}원", inline=False)
        
        for child in self.children:
            child.disabled = True
        self.children[0].label = "승인 완료됨"
        self.children[0].style = discord.ButtonStyle.secondary
        
        await interaction.message.edit(embed=embed, view=self)

        log_ch = bot.get_channel(CHARGE_LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="🏦 계좌 이체 충전 완료", description=f"<@{self.user_id}> 님의 계좌 이체 충전이 승인되었습니다.", color=0x3498db)
            embed.add_field(name="충전 금액", value=f"{self.amount}원")
            embed.add_field(name="현재 잔액", value=f"{user['balance']}원")
            await log_ch.send(embed=embed)

    @discord.ui.button(label="❌ 거절", style=discord.ButtonStyle.danger, custom_id="bank_reject_btn")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_USER_ID:
            return await interaction.response.send_message("❌ 관리자만 거절할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=False)
        
        for child in self.children:
            child.disabled = True
        self.children[1].label = "거절됨"
        
        await interaction.message.edit(content="❌ 충전 신청이 거절되었습니다.", view=self)

# ----------------- [UI: 상품 선택 및 자동 지급] -----------------
class QuantityModal(discord.ui.Modal):
    def __init__(self, item_name):
        super().__init__(title=f"[{item_name}] 수량 선택")
        self.item_name = item_name
        self.qty = discord.ui.TextInput(label="구매할 수량", placeholder="예: 1", required=True, max_length=3)
        self.add_item(self.qty)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            qty = int(self.qty.value)
            if qty <= 0: raise ValueError
        except ValueError: return await interaction.followup.send("❌ 1 이상의 숫자만 입력해주세요.", ephemeral=True)
        
        user = get_user(interaction.user.id); data = db["products"][self.item_name]
        
        if data["stock"] < qty: return await interaction.followup.send(f"❌ 재고 부족 (현재: {data['stock']}개)", ephemeral=True)
        total_price = data["price"] * qty
        if user["balance"] < total_price: return await interaction.followup.send(f"❌ 잔액 부족 (필요: {total_price}원 / 보유: {user['balance']}원)", ephemeral=True)
        
        delivery_items = data["delivery_data"][:qty] 
        data["delivery_data"] = data["delivery_data"][qty:]
        data["stock"] = len(data["delivery_data"])
        
        user["balance"] -= total_price
        user["total_spent"] = user.get("total_spent", 0) + total_price
        save_db()
        
        titles = data.get("delivery_titles", ["상품 지급 완료"])
        chosen_title = random.choice(titles) if titles else "상품 지급 완료"
        
        dm_embed = discord.Embed(title=f"🎁 {chosen_title}", description=f"구매하신 **{self.item_name}** 상품입니다.", color=0x2ecc71)
        delivery_text = "\n".join([f"`{item}`" for item in delivery_items])
        dm_embed.add_field(name="지급 데이터", value=delivery_text, inline=False)
        dm_embed.set_footer(text="이용해주셔서 감사합니다.")
        
        try:
            await interaction.user.send(embed=dm_embed)
            dm_success = True
        except:
            dm_success = False

        log_ch = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="💰 **자동 구매 발생**", color=0x2ecc71)
            embed.add_field(name="구매자", value=interaction.user.mention, inline=True)
            embed.add_field(name="상품", value=f"{self.item_name} (x{qty})", inline=True)
            embed.add_field(name="금액", value=f"{total_price}원", inline=True)
            embed.set_footer(text="자동 지급 완료" if dm_success else "DM 실패 (수동 지급 필요)")
            await log_ch.send(embed=embed)

        if dm_success:
            await interaction.followup.send(f"✅ 구매 완료! DM으로 상품이 지급되었습니다.", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ 구매는 완료되었으나 **DM 발송에 실패**했습니다. (DM 차단 해제 후 관리자에게 문의하세요)", ephemeral=True)

class ProductSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for name, data in db["products"].items():
            if data["stock"] > 0:
                options.append(discord.SelectOption(label=name, description=f"{data['price']}원 (재고: {data['stock']}개)", value=name))
        if not options: options = [discord.SelectOption(label="상품 없음", value="none")]
        super().__init__(placeholder="상품을 선택하세요", options=options)
    async def callback(self, interaction: discord.Interaction):
        item = self.values[0]
        if item == "none" or item not in db["products"]: return
        data = db["products"][item]
        embed = discord.Embed(title=f"📦 {item}", description=data['desc'], color=0x2b2d31)
        embed.add_field(name="가격", value=f"{data['price']}원", inline=True)
        embed.add_field(name="재고", value=f"{data['stock']}개", inline=True)
        view = discord.ui.View()
        if data['stock'] > 0:
            btn = discord.ui.Button(label="🛒 수량 선택 및 구매", style=discord.ButtonStyle.success, custom_id=f"buy_qty_{item}")
            btn.callback = self.buy_qty_callback
            view.add_item(btn)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    async def buy_qty_callback(self, interaction: discord.Interaction): await interaction.response.send_modal(QuantityModal(self.values[0]))

# ----------------- [UI: 장바구니] -----------------
class CartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60)
    @discord.ui.button(label="💳 일괄 결제", style=discord.ButtonStyle.success, custom_id="cart_checkout")
    async def checkout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = get_user(interaction.user.id)
        if not user["cart"]: return await interaction.followup.send("🛒 장바구니가 비어 있습니다.", ephemeral=True)
        
        total = sum(db["products"][item]["price"] for item in user["cart"] if item in db["products"])
        if user["balance"] < total: return await interaction.followup.send(f"❌ 잔액 부족 (필요: {total}원)", ephemeral=True)
        
        delivery_items = []
        for item_name in user["cart"]:
            if item_name in db["products"]:
                data = db["products"][item_name]
                if data["stock"] <= 0: return await interaction.followup.send(f"❌ `{item_name}` 재고가 부족합니다.", ephemeral=True)
                
                titles = data.get("delivery_titles", ["상품 지급 완료"])
                chosen_title = random.choice(titles) if titles else "상품 지급 완료"
                
                delivery_items.append((item_name, data["price"], data["delivery_data"].pop(0), chosen_title))
                data["stock"] = len(data["delivery_data"])
                
        user["balance"] -= total
        user["total_spent"] = user.get("total_spent", 0) + total
        user["cart"] = []
        save_db()
        
        dm_embed = discord.Embed(title="🎁 장바구니 상품 지급 완료", description="구매하신 상품 목록입니다.", color=0x2ecc71)
        for name, price, data, title in delivery_items:
            dm_embed.add_field(name=f"[{title}] {name} ({price}원)", value=f"`{data}`", inline=False)
            
        try:
            await interaction.user.send(embed=dm_embed)
            dm_success = True
        except:
            dm_success = False

        log_ch = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"💰 **장바구니 구매** | {interaction.user.mention} 님이 {len(delivery_items)}개 상품 구매 (자동 지급)")
            
        if dm_success:
            await interaction.followup.send(f"✅ 장바구니 결제 완료! DM을 확인해주세요.", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ 결제는 완료되었으나 DM 발송에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="🗑️ 비우기", style=discord.ButtonStyle.danger, custom_id="cart_clear")
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id); user["cart"] = []; save_db()
        await interaction.response.send_message("🗑️ 장바구니를 비웠습니다.", ephemeral=True)

# ----------------- [명령어] -----------------
@bot.command()
@commands.has_permissions(administrator=True)
async def 패널생성(ctx):
    admin_ch = bot.get_channel(ADMIN_CHANNEL_ID)
    if admin_ch:
        embed = discord.Embed(title="🛠️ 상품 관리 시스템", description="상품 등록, 재고 추가, 쿠폰 생성을 관리합니다.", color=0x9b59b6)
        await admin_ch.send(embed=embed, view=AdminPanelView())
    shop_ch = bot.get_channel(SHOP_CHANNEL_ID)
    if shop_ch:
        embed = discord.Embed(title="🛒 서버 상점", description="아래 버튼을 눌러 이용하세요.", color=0x2b2d31)
        await shop_ch.send(embed=embed, view=ShopDashboardView())
        
    support_ch = bot.get_channel(SUPPORT_TICKET_CHANNEL_ID)
    if support_ch:
        embed = discord.Embed(title="📩 1:1 문의", description="아래 버튼을 눌러 스태프와 1:1 문의를 진행하세요.", color=0x3498db)
        await support_ch.send(embed=embed, view=TicketCreateView())
        
    await ctx.send("✅ 패널 생성 완료! (기존 패널은 삭제해주세요)")

@bot.command()
async def 장바구니(ctx):
    user = get_user(ctx.author.id)
    if not user["cart"]: return await ctx.send("🛒 장바구니가 비어 있습니다.")
    desc = ""; total = 0
    for item in user["cart"]:
        if item in db["products"]: desc += f"• {item} ({db['products'][item]['price']}원)\n"; total += db["products"][item]["price"]
    embed = discord.Embed(title="🛒 내 장바구니", description=desc, color=0x3498db); embed.set_footer(text=f"총 금액: {total}원")
    await ctx.send(embed=embed, view=CartView())

@bot.command()
async def 잔액(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 {ctx.author.mention} 님의 현재 잔액은 **{user['balance']}원** 입니다.")

@bot.command()
async def 티켓닫기(ctx):
    if "구매-" in ctx.channel.name or "충전-" in ctx.channel.name or "문의-" in ctx.channel.name:
        await ctx.send("🔒 3초 뒤 티켓이 닫힙니다."); await asyncio.sleep(3); await ctx.channel.delete()

@bot.event
async def on_ready():
    load_db()
    print(f"✅ 상점 봇 로그인 성공: {bot.user}")
    bot.add_view(AdminPanelView()); bot.add_view(ShopDashboardView())
    bot.add_view(TicketCreateView())
    print("✅ 뷰 등록 완료")

if __name__ == "__main__":
    bot.run(TOKEN)
