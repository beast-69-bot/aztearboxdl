import os
import re
import uuid
import asyncio
from dotenv import load_dotenv
from curl_cffi import requests as curl_requests
from pyrogram import Client, filters, idle
from pyrogram.types import Message

# Load environment variables from .env file
load_dotenv()

# ==========================================
# CONFIGURATION (loaded from .env file)
# ==========================================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
NDUS_COOKIE = os.getenv("NDUS_COOKIE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Initialize Pyrogram Client
app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_terabox_data(surl: str):
    """
    Extracts the direct download link from TeraBox using curl_cffi.
    """
    short_url = surl[1:] if surl.startswith("1") else surl
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    }

    first_url = f"https://dm.terabox.app/sharing/link?surl={short_url}"
    response = session.get(first_url, headers=headers)

    match = re.search(r'fn%28%22(.*?)%22%29', response.text)
    if not match:
        return None
        
    jsToken = match.group(1)
    api_url = "https://dm.terabox.app/share/list"

    params = {
        "app_id": "250528",
        "jsToken": jsToken,
        "site_referer": "https://www.terabox.app/",
        "shorturl": short_url,
        "root": "1"
    }

    api_headers = {
        "Host": "dm.terabox.app",
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://dm.terabox.app/sharing/link?surl={short_url}&clearCache=1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://dm.terabox.app"
    }

    api_response = session.get(api_url, params=params, headers=api_headers)
    return api_response.json()


import time
import math

# Progress Bar Config
last_update_time = {}

def get_progress_bar(current, total):
    percentage = current * 100 / total
    progress = int(percentage / 5)
    bar = "█" * progress + "░" * (20 - progress)
    return f"[{bar}] {percentage:.1f}%"

def format_bytes(size):
    if not size:
        return "0 B"
    power = 2 ** 10
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

async def progress_callback(current, total, message: Message, action: str, filename: str, start_time: float):
    global last_update_time
    msg_id = message.id
    
    # Update only every 3 seconds to avoid FloodWait
    now = time.time()
    if msg_id in last_update_time and (now - last_update_time[msg_id]) < 3.0:
        if current != total:
            return
            
    last_update_time[msg_id] = now
    
    elapsed_time = now - start_time
    if elapsed_time == 0:
        elapsed_time = 0.1
    speed = current / elapsed_time
    
    # Prevent division by zero for ETA
    if speed == 0:
        speed = 1
        
    eta = (total - current) / speed
    
    text = (
        f"⏳ **{action}...**\n"
        f"📁 `{filename}`\n\n"
        f"{get_progress_bar(current, total)}\n"
        f"🚀 **Speed:** {format_bytes(speed)}/s\n"
        f"📦 **Size:** {format_bytes(current)} / {format_bytes(total)}\n"
        f"⏱ **ETA:** {int(eta)}s"
    )
    
    try:
        await message.edit_text(text)
    except Exception:
        pass


async def download_file(dlink, filename, message: Message, total_size: int):
    """
    Downloads the file from TeraBox to the VPS local storage in chunks with progress.
    """
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    
    req = session.get(dlink, headers=headers, stream=True)
    if req.status_code != 200:
        raise Exception(f"Failed to connect to TeraBox download server. Status: {req.status_code}")

    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{filename}"
    os.makedirs("downloads", exist_ok=True)

    start_time = time.time()
    downloaded = 0
    
    with open(filepath, 'wb') as f:
        for chunk in req.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                # Update download progress
                await progress_callback(
                    current=downloaded,
                    total=total_size,
                    message=message,
                    action="Downloading to VPS",
                    filename=filename,
                    start_time=start_time
                )
                
    return filepath


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "myid"]))
async def handle_link(client, message: Message):
    text = message.text
    urls = re.findall(r'(https?://[^\s]+)', text)
    
    if not urls:
        error_text = (
            "❌ **Invalid TeraBox Link**\n\n"
            "Please send a public\n"
            "`1024tera.com`\n"
            "or\n"
            "`terasharefile.com`\n"
            "link.\n\n"
            "Example:\n"
            "`https://1024tera.com/s/...`"
        )
        await message.reply_text(error_text)
        return

    url = urls[0]
    surl_match = re.search(r'/s/([A-Za-z0-9_-]+)', url)
    if not surl_match:
        await message.reply_text("❌ Could not extract ID. Make sure it's a valid TeraBox shortlink.")
        return
        
    surl = surl_match.group(1)
    
    status_msg = await message.reply_text("🔍 Validating Link...")
    await asyncio.sleep(0.5)
    await status_msg.edit_text("📥 Extracting Stream...")

    try:
        data = get_terabox_data(surl)
        if not data or data.get("errno") != 0 or not data.get("list"):
            await status_msg.edit_text("❌ Failed to extract. The file might be deleted or private.")
            return
            
        file_info = data["list"][0]
        filename = file_info.get("server_filename", "Unknown_Video.mp4")
        dlink = file_info.get("dlink")
        total_size = int(file_info.get("size", 0))
        size_mb = total_size / (1024 * 1024)
        
        if size_mb > 2000:
            await status_msg.edit_text("❌ Error: File is larger than 2GB (Telegram Limit).")
            return

        await status_msg.edit_text("⚡ Generating Download...")
        await asyncio.sleep(0.5)
        
        # 1. Download to VPS (with progress)
        local_filepath = await download_file(dlink, filename, status_msg, total_size)
        
        # 2. Upload to Telegram (with progress)
        upload_start_time = time.time()
        
        caption = (
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ **AZ STREAM**\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🎬 **{filename}**\n\n"
            f"📦 **{size_mb:.2f} MB**\n\n"
            "🟢 **Ready**\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ VPS Hosted\n"
            "🚫 No Ads\n"
            "♾ Unlimited Speed\n\n"
            "Powered by AZ Network"
        )
        
        await client.send_video(
            chat_id=message.chat.id,
            video=local_filepath,
            caption=caption,
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(status_msg, "Uploading to Telegram", filename, upload_start_time)
        )
        
        await status_msg.delete()
        
        # Cleanup VPS storage
        if os.path.exists(local_filepath):
            os.remove(local_filepath)

    except Exception as e:
        await status_msg.edit_text(f"⚠️ An error occurred: {str(e)}")

@app.on_message(filters.command("myid") & filters.private)
async def my_id_command(client, message: Message):
    await message.reply_text(f"🆔 Your Telegram User ID: `{message.from_user.id}`")

async def send_startup_notification():
    """Sends a startup message to the admin when bot restarts."""
    import datetime
    now = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    try:
        await app.send_message(
            ADMIN_ID,
            f"✅ **AZ Stream Bot — Online!**\n\n"
            f"🕐 Time: `{now}`\n"
            f"🖥 VPS: `209.38.105.80`\n"
            f"🤖 Status: Online & Ready\n\n"
            f"Powered by AZ Network"
        )
        print(f"Startup notification sent to {ADMIN_ID}")
    except Exception as e:
        print(f"Failed to send startup notification: {e}")

@app.on_message(filters.command(["start", "help"]))
async def start_command(client, message: Message):
    welcome_text = (
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ **AZ STREAM BOT**\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👋 Welcome! Send me any TeraBox link, and I will upload the file directly here.\n\n"
        "⚡ Instant VPS Download\n"
        "🚫 No Ads\n"
        "♾ Unlimited Speed\n\n"
        "Powered by AZ Network"
    )
    await message.reply_text(welcome_text)

async def on_startup():
    await send_startup_notification()
    print("Bot is running... Press Ctrl+C to stop.")

if __name__ == "__main__":
    print("Starting Pyrogram TeraBox Bot...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.start())
    loop.run_until_complete(on_startup())
    loop.run_until_complete(idle())
    loop.run_until_complete(app.stop())
