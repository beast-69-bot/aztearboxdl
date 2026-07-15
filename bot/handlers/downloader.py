import re
import os
import time
import asyncio
import sys
import logging
from dotenv import load_dotenv
from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from bot.utils.terabox import get_terabox_info, download_file, check_ndus_cookie
from bot.utils.progress import progress_callback
from bot.utils.database import add_user, increment_stat
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Path configuration for cookie refresher relative to downloader.py
BOT_HANDLERS_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(BOT_HANDLERS_DIR)
BOT_ROOT_DIR = os.path.dirname(BOT_DIR)
ROOT_DIR = os.path.dirname(BOT_ROOT_DIR)

REFRESH_SCRIPT = os.path.join(ROOT_DIR, "refresh_cookies.py")
BOT_ENV_PATH = os.path.join(BOT_ROOT_DIR, ".env")

if sys.platform == "win32":
    VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "bin", "python")

python_exe = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable

async def trigger_cookie_refresh() -> bool:
    """Runs the refresh_cookies.py script to refresh ndus cookie."""
    logger.info(f"Triggering auto login / refresh script: {python_exe} {REFRESH_SCRIPT}")
    try:
        proc = await asyncio.create_subprocess_exec(
            python_exe, REFRESH_SCRIPT, "--headless",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="ignore")
        stderr_str = stderr.decode("utf-8", errors="ignore")
        
        logger.info(f"Refresh Script stdout: {stdout_str}")
        if proc.returncode == 0:
            logger.info("Cookie refresh script ran successfully!")
            # Reload env variables
            load_dotenv(BOT_ENV_PATH, override=True)
            import config
            config.NDUS_COOKIE = os.getenv("NDUS_COOKIE")
            logger.info("Reloaded NDUS_COOKIE successfully!")
            return True
        else:
            logger.error(f"Cookie refresh script failed (exit code {proc.returncode})")
            logger.error(f"Stderr: {stderr_str}")
    except Exception as e:
        logger.error(f"Failed to execute cookie refresh: {e}", exc_info=True)
    return False


async def delete_message_after_delay(client, chat_id: int, message_id: int, delay: int):
    """Waits for specified delay and deletes the target message."""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=message_id)
        print(f"Auto-deleted message {message_id} in chat {chat_id} after {delay} seconds.")
    except Exception as e:
        print(f"Failed to auto-delete message {message_id} in chat {chat_id}: {e}")


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "myid", "broadcast", "stats"]))
async def handle_link(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)  # Save active user to database

    text = message.text
    urls = re.findall(r"(https?://[^\s]+)", text)

    if not urls:
        error_text = (
            "<b>✖️ ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a public link from:\n"
            "▸ <code>1024tera.com</code>\n"
            "▸ <code>terasharefile.com</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Example: https://1024tera.com/s/...</i>"
        )
        await message.reply_text(error_text)
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
                "<b>⚑ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "You have used your free limit of <b>10 links per day</b>.\n\n"
                "💸 Want unlimited links & faster processing?\n"
                "Go to @azofficialmainbot to buy Premium! ⭐\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            await message.reply_text(limit_msg)
            return

    url = urls[0]
    match = re.search(r"/s/([A-Za-z0-9_-]+)", url)
    if not match:
        await message.reply_text("<b>✖️ ᴇxᴛʀᴀᴄᴛɪᴏɴ ᴇʀʀᴏʀ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nCould not extract file ID. Send a valid TeraBox shortlink.")
        return

    surl = match.group(1)
    status = await message.reply_text("<b>🔍 ᴠᴀʟɪᴅᴀᴛɪɴɢ ʟɪɴᴋ...</b>")


    # ── Fetch file info ──────────────────────────────────────────────
    await status.edit_text("<b>📥 ᴇxᴛʀᴀᴄᴛɪɴɢ ɪɴꜰᴏ...</b>")
    info = await asyncio.to_thread(get_terabox_info, surl)

    if not info:
        # Check if cookie has expired/invalid (internally triggers auto-refresh if needed)
        is_cookie_valid = await asyncio.to_thread(check_ndus_cookie)
        if is_cookie_valid:
            await status.edit_text("✅ **Cookies refreshed successfully!** Retrying extraction...")
            await asyncio.sleep(1)
            info = await asyncio.to_thread(get_terabox_info, surl)
        else:
            await status.edit_text("❌ **Auto cookie refresh failed!** Please log in manually or check logs.")
            return

    if not info:
        await status.edit_text("<b>✖️ ᴇxᴛʀᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nFile may be deleted or set to private.")
        return

    filename = info["filename"]
    total_size = info["size"]
    dlink = info["dlink"]
    size_mb = total_size / (1024 * 1024)

    if size_mb > 2000:
        await status.edit_text("<b>✖️ ꜰɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nFile exceeds 2 GB Telegram limit.")
        return

    # ── Download to VPS ──────────────────────────────────────────────
    await status.edit_text(f"<b>⬇️ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n▸ <b>ꜰɪʟᴇ</b>: <code>{filename}</code>")
    try:
        local_path = await download_file(dlink, filename, status, total_size)
        increment_stat("downloads")  # Increment downloads stat
    except Exception as e:
        await status.edit_text(f"<b>✖️ ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<code>{e}</code>")
        return

    # ── Upload to Telegram ───────────────────────────────────────────
    upload_start = time.time()
    caption = (
        "<b>🎬 ꜱᴛʀᴇᴀᴍ ʀᴇᴀᴅʏ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"▸ <b>ꜰɪʟᴇ</b>: <code>{filename}</code>\n"
        f"▸ <b><b>ꜱɪᴢᴇ</b></b>: <code>{size_mb:.2f} MB</code>\n"
        "▸ <b>⏳ Auto Delete:</b> <code>Active (20 mins)</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ VPS Hosted | 🚫 No Ads | ♾ Unlimited Speed\n"
        "<i>Powered by</i> @az_hawas_adda 🔥"
    )
    
    # Use PNG first to avoid JPEG compression quality loss
    thumb_png = os.path.join(os.path.dirname(__file__), "..", "utils", "thumbnail.png")
    thumb_jpg = os.path.join(os.path.dirname(__file__), "..", "utils", "thumbnail.jpg")
    if os.path.exists(thumb_png):
        thumb_path = thumb_png
    elif os.path.exists(thumb_jpg):
        thumb_path = thumb_jpg
    else:
        thumb_path = None

    try:
        sent_video = await client.send_video(
            chat_id=message.chat.id,
            video=local_path,
            caption=caption,
            supports_streaming=True,
            thumb=thumb_path,
            progress=progress_callback,
            progress_args=(status, "Uploading to Telegram", filename, upload_start),
        )
        await status.delete()
        increment_stat("uploads")  # Increment uploads stat
        
        # Start background task to delete the message after 20 minutes (1200 seconds)
        asyncio.create_task(delete_message_after_delay(client, message.chat.id, sent_video.id, 1200))
        
        # Increment usage count upon successful completion
        if user_id != ADMIN_ID:
            app.user_limits[user_id] = app.user_limits.get(user_id, 0) + 1
            remaining = 10 - app.user_limits[user_id]
            success_msg = (
                "<b>✔ ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"▸ <b>ʀᴇᴍᴀɪɴɪɴɢ ʟɪᴍɪᴛ</b>: <code>{remaining}/10</code>\n"
                "▸ ⚠️ <i>This video will auto-delete in 20 minutes!</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            await message.reply_text(success_msg)
        else:
            admin_msg = (
                "<b>✔ ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "▸ ⚠️ <i>This video will auto-delete in 20 minutes!</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            await message.reply_text(admin_msg)
    except Exception as e:
        await status.edit_text(f"<b>✖️ ᴜᴘʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<code>{e}</code>")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
