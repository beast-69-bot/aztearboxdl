from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from config import ADMIN_ID


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client, message: Message):
    text = (
        "<b>⚡ ᴀᴢ ꜱᴛʀᴇᴀᴍ ʙᴏᴛ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👋 Welcome! Send me any TeraBox link, and I will upload the file directly here.\n\n"
        "▸ <b>ꜱᴘᴇᴇᴅ</b>: <code>Unlimited</code>\n"
        "▸ <b>ᴀᴅꜱ</b>: <code>Disabled</code>\n"
        "▸ <b>ʜᴏꜱᴛɪɴɢ</b>: <code>Dedicated VPS</code>\n\n"
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
