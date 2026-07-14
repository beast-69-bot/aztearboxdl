import os
import re
import json
import uuid
import threading
from flask import Flask, request, Response
import telebot
from curl_cffi import requests as curl_requests

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = "7899193078:AAFvbxq8AqijIoLu3eJHv5GCXk1x8byqITA"
# TeraBox 'ndus' cookie value from your logged-in browser
NDUS_COOKIE = "YSkeXKjteHuioD6j7V0PlO3TC8wHJK1hA7q9yu5o"
# Your VPS IP (Replace with your actual VPS public IP or Domain)
VPS_IP = "YOUR_VPS_IP"  # e.g., "198.51.100.23"
PORT = 8080

# ==========================================

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# In-memory dictionary to store generated links mapping
# { 'unique_id': {'dlink': '...', 'filename': '...'} }
links_db = {}

def get_terabox_data(surl: str):
    """
    Extracts the direct download link from TeraBox using curl_cffi to bypass bot protections.
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


# --- FLASK WEB SERVER FOR PROXY STREAMING ---
@app.route('/dl/<file_id>')
def download_proxy(file_id):
    if file_id not in links_db:
        return "Link expired or not found.", 404
        
    file_info = links_db[file_id]
    dlink = file_info['dlink']
    filename = file_info['filename']
    
    # We use curl_cffi to fetch the actual video stream
    # Pass the same cookies and User-Agent so TeraBox trusts us
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    
    # Send request with stream=True
    req = session.get(dlink, headers=headers, stream=True)
    
    if req.status_code != 200:
        return f"TeraBox returned error: {req.status_code}", 500

    def generate():
        # Stream the content in chunks directly to the user's browser
        for chunk in req.iter_content(chunk_size=1024 * 64): # 64KB chunks
            if chunk:
                yield chunk

    # Return the Flask streaming response
    return Response(
        generate(),
        headers={
            'Content-Type': req.headers.get('Content-Type', 'application/octet-stream'),
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': req.headers.get('Content-Length')
        }
    )


# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Send me a TeraBox link!\nI will generate a direct Proxy Stream link that bypasses all limits and Ads.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text
    urls = re.findall(r'(https?://[^\s]+)', text)
    
    if not urls:
        bot.reply_to(message, "Please send a valid TeraBox link. 🔗")
        return

    url = urls[0]
    surl_match = re.search(r'/s/([A-Za-z0-9_-]+)', url)
    if not surl_match:
        bot.reply_to(message, "Could not extract ID. Format should be terabox.app/s/...")
        return
        
    surl = surl_match.group(1)
    status_msg = bot.reply_to(message, "⏳ Extracting and preparing Proxy Stream...")

    try:
        data = get_terabox_data(surl)
        if not data or data.get("errno") != 0 or not data.get("list"):
            bot.edit_message_text("❌ Failed. File might be deleted, or cookie is expired.", 
                                  chat_id=message.chat.id, message_id=status_msg.message_id)
            return
            
        file_info = data["list"][0]
        filename = file_info.get("server_filename", "Video.mp4")
        size_mb = int(file_info.get("size", 0)) / (1024 * 1024)
        raw_dlink = file_info.get("dlink")
        
        # Create a unique ID for our proxy server
        file_id = str(uuid.uuid4())[:8]
        links_db[file_id] = {
            "dlink": raw_dlink,
            "filename": filename
        }
        
        # Build the final link for the user
        proxy_url = f"http://{VPS_IP}:{PORT}/dl/{file_id}"
        
        reply_text = (
            f"✅ **Stream/Download Ready!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"⚖️ **Size:** `{size_mb:.2f} MB`\n\n"
            f"🔗 [CLICK HERE TO FAST DOWNLOAD]({proxy_url})\n\n"
            f"*(No Ads | Bypassed Telegram Limit | Hosted on VPS)*"
        )
        
        bot.edit_message_text(reply_text, chat_id=message.chat.id, 
                              message_id=status_msg.message_id, parse_mode="Markdown",
                              disable_web_page_preview=True)

    except Exception as e:
        bot.edit_message_text(f"⚠️ Error: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)

def run_bot():
    print("Bot is starting...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Start bot in a separate background thread
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Start Flask Web Server on the main thread
    print(f"Starting Proxy Web Server on Port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
