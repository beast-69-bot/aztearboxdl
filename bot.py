import os
import re
import uuid
import asyncio
from curl_cffi import requests as curl_requests
from pyrogram import Client, filters
from pyrogram.types import Message

# ==========================================
# CONFIGURATION
# ==========================================
API_ID = 37984186
API_HASH = "f1525a5c408ab147efe4c888f4b08c1a"
BOT_TOKEN = "7899193078:AAFvbxq8AqijIoLu3eJHv5GCXk1x8byqITA"
NDUS_COOKIE = "YSkeXKjteHuioD6j7V0PlO3TC8wHJK1hA7q9yu5o"

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


async def download_file(dlink, filename, message: Message):
    """
    Downloads the file from TeraBox to the VPS local storage in chunks.
    Returns the local filepath.
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

    # Generate a unique path to avoid collisions
    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{filename}"
    os.makedirs("downloads", exist_ok=True)

    # Status update
    await message.edit_text(f"⏳ **Downloading to VPS Server...**\n📁 File: `{filename}`")

    # Download in chunks
    with open(filepath, 'wb') as f:
        for chunk in req.iter_content(chunk_size=1024 * 1024): # 1MB chunks
            if chunk:
                f.write(chunk)
                
    return filepath


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

@app.on_message(filters.text & filters.private)
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
    
    # Progress: Validating
    status_msg = await message.reply_text("🔍 Validating Link...")
    await asyncio.sleep(0.5)
    
    # Progress: Extracting
    await status_msg.edit_text("📥 Extracting Stream...")

    try:
        data = get_terabox_data(surl)
        if not data or data.get("errno") != 0 or not data.get("list"):
            await status_msg.edit_text("❌ Failed to extract. The file might be deleted or private.")
            return
            
        file_info = data["list"][0]
        filename = file_info.get("server_filename", "Unknown_Video.mp4")
        dlink = file_info.get("dlink")
        size_mb = int(file_info.get("size", 0)) / (1024 * 1024)
        
        if size_mb > 2000:
            await status_msg.edit_text("❌ Error: File is larger than 2GB (Telegram Limit).")
            return

        # Progress: Generating
        await status_msg.edit_text("⚡ Generating Download...")
        await asyncio.sleep(0.5)
        
        # 1. Download to VPS
        await status_msg.edit_text(f"⏳ **Downloading to VPS Server...**\n📁 `{filename}`")
        local_filepath = await download_file(dlink, filename, status_msg)
        
        # 2. Upload to Telegram
        await status_msg.edit_text(f"🚀 **Uploading to Telegram...**\n📁 `{filename}`")
        
        # Premium AZ Network Caption
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
            supports_streaming=True
        )
        
        await status_msg.delete()
        
        # 3. Cleanup VPS storage
        if os.path.exists(local_filepath):
            os.remove(local_filepath)

    except Exception as e:
        await status_msg.edit_text(f"⚠️ An error occurred: {str(e)}")

if __name__ == "__main__":
    print("Starting Pyrogram TeraBox Bot...")
    app.run()
