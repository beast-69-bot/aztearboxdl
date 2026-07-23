import re
import os
import time
import asyncio
from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from bot.utils.terabox import get_terabox_info, download_file
from bot.utils.progress import progress_callback
from bot.utils.database import add_user, increment_stat, check_faphouse_premium
from bot.utils.rate_limiter import RequestGuard, RateLimitExceeded
from config import ADMIN_ID


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
    add_user(user_id)

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

    # ── Daily limit check ─────────────────────────────────────────────
    current_date = time.strftime("%Y-%m-%d")
    if not hasattr(app, "user_limits"):
        app.user_limits = {}
    if not hasattr(app, "limit_date") or app.limit_date != current_date:
        app.user_limits = {}
        app.limit_date = current_date

    if user_id != ADMIN_ID:
        user_usage = app.user_limits.get(user_id, 0)
        if user_usage >= 10:
            # Check if they have active FapHouse plan (FapHouse users get unlimited downloads!)
            has_premium = await check_faphouse_premium(user_id)
            if not has_premium:
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

    # ── Rate Limit Guard (prevents account flagging) ──────────────────
    try:
        async with RequestGuard(user_id):
            await _process_download(client, message, user_id, surl)
    except RateLimitExceeded as e:
        msg = (
            f"<b>⏳ ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{e}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.reply_text(msg)


async def _process_download(client, message: Message, user_id: int, surl: str):
    """Core download-upload flow. Always called inside RequestGuard."""
    status = await message.reply_text("<b>🔍 ᴠᴀʟɪᴅᴀᴛɪɴɢ ʟɪɴᴋ...</b>")

    # ── Fetch file info ───────────────────────────────────────────────
    await status.edit_text("<b>📥 ᴇxᴛʀᴀᴄᴛɪɴɢ ɪɴꜰᴏ...</b>")
    info = await asyncio.to_thread(get_terabox_info, surl)

    if not info:
        await status.edit_text("<b>✖️ ᴇxᴛʀᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nCould not extract download link. The link might be expired, private, or invalid.")
        return

    filename  = info["filename"]
    total_size = info["size"]
    dlink     = info["dlink"]
    referer   = info.get("referer")
    origin    = info.get("origin")
    size_mb   = total_size / (1024 * 1024)

    if size_mb > 2000:
        await status.edit_text("<b>✖️ ꜰɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\nFile exceeds 2 GB Telegram limit.")
        return

    # ── Download to VPS ───────────────────────────────────────────────
    await status.edit_text(f"<b>⬇️ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n▸ <b>ꜰɪʟᴇ</b>: <code>{filename}</code>")
    try:
        local_path = await download_file(dlink, filename, status, total_size, referer=referer, origin=origin)
        increment_stat("downloads")
    except Exception as e:
        await status.edit_text(f"<b>✖️ ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<code>{e}</code>")
        return

    # ── Upload to Telegram ────────────────────────────────────────────
    upload_start = time.time()
    caption = (
        "<b>🎬 ꜱᴛʀᴇᴀᴍ ʀᴇᴀᴅʏ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"▸ <b>ꜰɪʟᴇ</b>: <code>{filename}</code>\n"
        f"▸ <b>ꜱɪᴢᴇ</b>: <code>{size_mb:.2f} MB</code>\n"
        "▸ <b>⏳ Auto Delete:</b> <code>Active (20 mins)</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ VPS Hosted | 🚫 No Ads | ♾ Unlimited Speed\n"
        "<i>Powered by</i> @az_hawas_adda 🔥"
    )

    thumb_png = os.path.join(os.path.dirname(__file__), "..", "utils", "thumbnail.png")
    thumb_jpg = os.path.join(os.path.dirname(__file__), "..", "utils", "thumbnail.jpg")
    thumb_path = thumb_png if os.path.exists(thumb_png) else (thumb_jpg if os.path.exists(thumb_jpg) else None)

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
        increment_stat("uploads")

        asyncio.create_task(delete_message_after_delay(client, message.chat.id, sent_video.id, 1200))

        # Check Premium status
        is_premium = False
        is_faphouse_premium = False
        
        if user_id == ADMIN_ID:
            is_premium = True
        else:
            # Check FapHouse active plan from shared MongoDB database
            is_faphouse_premium = await check_faphouse_premium(user_id)
            if is_faphouse_premium:
                is_premium = True

        if not is_premium:
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
            plan_name = "FapHouse Bonus (Unlimited)" if is_faphouse_premium else "Admin (Unlimited)"
            premium_msg = (
                "<b>✔ ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"▸ <b>ᴘʟᴀɴ</b>: <code>{plan_name}</code> ⭐\n"
                "▸ ⚠️ <i>This video will auto-delete in 20 minutes!</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            await message.reply_text(premium_msg)
            
    except Exception as e:
        await status.edit_text(f"<b>✖️ ᴜᴘʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n<code>{e}</code>")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

