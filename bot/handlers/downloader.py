import re
import os
import time
from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from bot.utils.terabox import get_terabox_info, download_file
from bot.utils.progress import progress_callback
from config import ADMIN_ID


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "myid"]))
async def handle_link(client, message: Message):
    text = message.text
    urls = re.findall(r"(https?://[^\s]+)", text)

    if not urls:
        await message.reply_text(
            "❌ **Invalid TeraBox Link**\n\n"
            "Please send a public\n"
            "`1024tera.com`\nor\n`terasharefile.com`\nlink.\n\n"
            "Example:\n`https://1024tera.com/s/...`"
        )
        return

    user_id = message.from_user.id
    
    # Simple in-memory limit tracking
    current_date = time.strftime("%Y-%m-%d")
    
    # Initialize trackers if not present
    if not hasattr(app, "user_limits"):
        app.user_limits = {}
    if not hasattr(app, "limit_date") or app.limit_date != current_date:
        app.user_limits = {}
        app.limit_date = current_date
        
    # Check limit if the user is not the admin
    if user_id != ADMIN_ID:
        user_usage = app.user_limits.get(user_id, 0)
        if user_usage >= 10:
            limit_msg = (
                "🚨 **Daily Limit Reached!**\n\n"
                "You have used your free limit of **10 links per day**.\n\n"
                "💸 Want unlimited links & faster processing?\n"
                "Go to **@azofficialmainbot** to buy Premium! ⭐"
            )
            await message.reply_text(limit_msg)
            return

    url = urls[0]
    match = re.search(r"/s/([A-Za-z0-9_-]+)", url)
    if not match:
        await message.reply_text("❌ Could not extract file ID. Send a valid TeraBox shortlink.")
        return

    surl = match.group(1)
    status = await message.reply_text("🔍 Validating link...")


    # ── Fetch file info ──────────────────────────────────────────────
    await status.edit_text("📥 Extracting file info...")
    info = get_terabox_info(surl)

    if not info:
        await status.edit_text("❌ Failed to extract. File may be deleted or set to private.")
        return

    filename = info["filename"]
    total_size = info["size"]
    dlink = info["dlink"]
    size_mb = total_size / (1024 * 1024)

    if size_mb > 2000:
        await status.edit_text("❌ File exceeds 2 GB Telegram limit.")
        return

    # ── Download to VPS ──────────────────────────────────────────────
    await status.edit_text(f"⬇️ **Downloading to VPS...**\n📁 `{filename}`")
    try:
        local_path = await download_file(dlink, filename, status, total_size)
    except Exception as e:
        await status.edit_text(f"⚠️ Download failed: {e}")
        return

    # ── Upload to Telegram ───────────────────────────────────────────
    upload_start = time.time()
    caption = (
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ **AZ STREAM**\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 **{filename}**\n\n"
        f"📦 **{size_mb:.2f} MB**\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ VPS Hosted\n"
        "🚫 No Ads\n"
        "♾ Unlimited Speed\n\n"
        "Powered by AZ Network"
    )

    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=local_path,
            caption=caption,
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(status, "Uploading to Telegram", filename, upload_start),
        )
        await status.delete()
        
        # Increment usage count upon successful completion
        if user_id != ADMIN_ID:
            app.user_limits[user_id] = app.user_limits.get(user_id, 0) + 1
            remaining = 10 - app.user_limits[user_id]
            await message.reply_text(f"✅ **File processed successfully!**\nRemaining Free Links for Today: **{remaining}/10**")
    except Exception as e:
        await status.edit_text(f"⚠️ Upload failed: {e}")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
