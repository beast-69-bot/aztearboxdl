from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from bot.utils.database import add_user, get_stats, get_all_users
from config import ADMIN_ID
import asyncio


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)  # Save active user to database
    text = (
        "<b>⚡ ᴀᴢ ꜱᴛʀᴇᴀᴍ ʙᴏᴛ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👋 Welcome! Send me any TeraBox link, and I will upload the file directly here.\n\n"
        "▸ <b>ꜱᴘᴇᴇᴅ</b>: <code>Unlimited</code>\n"
        "▸ <b>ᴀᴅꜱ</b>: <code>Disabled</code>\n"
        "▸ <b>ʜᴏꜱᴛɪɴɢ</b>: <code>Dedicated VPS</code>\n"
        "▸ <b>ꜰʀᴇᴇ ʟɪᴍɪᴛ</b>: <code>10 links/day</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>FREE UNLIMITED BONUS!</b>\n"
        "@azofficialmainbot se <b>FapHouse</b> ka koi bhi plan lo\n"
        "→ Is bot pe <b>Unlimited downloads</b> FREE milenge! ♾️⭐\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Powered by AZ Network</i>"
    )
    await message.reply_text(text)



@app.on_message(filters.command("myid") & filters.private)
async def myid_command(client, message: Message):
    await message.reply_text(
        "<b>🆔 ᴜꜱᴇʀ ɪᴅ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"▸ <b>ʏᴏᴜʀ ɪᴅ</b>: <code>{message.from_user.id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )


@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message: Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    active_users, downloads, uploads = get_stats()
    stats_msg = (
        "<b>📊 ʙᴏᴛ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"▸ <b>ᴀᴄᴛɪᴠᴇ ᴜꜱᴇʀꜱ</b>: <code>{active_users}</code>\n"
        f"▸ <b>ᴅᴏᴡɴʟᴏᴀᴅꜱ</b>: <code>{downloads}</code>\n"
        f"▸ <b>ᴜᴘʟᴏᴀᴅꜱ</b>: <code>{uploads}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.reply_text(stats_msg)


@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message: Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.reply_text("<i>❌ Reply to a message to broadcast it.</i>")
        return

    broadcast_msg = message.reply_to_message
    users = get_all_users()

    status = await message.reply_text("<b>🚀 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴛᴀʀᴛᴇᴅ...</b>")
    
    success = 0
    failed = 0
    
    for u_id in users:
        try:
            await broadcast_msg.copy(chat_id=u_id)
            success += 1
            await asyncio.sleep(0.1)  # avoid flood limits
        except Exception:
            failed += 1

    await status.edit_text(
        "<b>📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜰɪɴɪꜱʜᴇᴅ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"▸ <b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ</b>: <code>{success}</code>\n"
        f"▸ <b>ꜰᴀɪʟᴇᴅ</b>: <code>{failed}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

