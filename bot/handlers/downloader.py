import re
import os
import time
from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from bot.utils.terabox import get_terabox_info, download_file
from bot.utils.progress import progress_callback
from bot.utils.database import add_user, increment_stat
from config import ADMIN_ID


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
    import asyncio
    info = await asyncio.to_thread(get_terabox_info, surl)

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
        f"▸ <b>ꜱɪᴢᴇ</b>: <code>{size_mb:.2f} MB</code>\n\n"
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
        await client.send_video(
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
        
        # Increment usage count upon successful completion
        if user_id != ADMIN_ID:
            app.user_limits[user_id] = app.user_limits.get(user_id, 0) + 1
            remaining = 10 - app.user_limits[user_id]
            success_msg = (
                "<b>✔ ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"▸ <b>ʀᴇᴍᴀɪɴɪɴɢ ʟɪᴍɪᴛ</b>: <code>{remaining}/10</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            await message.reply_text(success_msg)
    except Exception as e:
        await status.edit_text(f"<b>✖️ ᴜᴘʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<code>{e}</code>")

    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

