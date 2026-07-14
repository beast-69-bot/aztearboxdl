from pyrogram import filters
from pyrogram.types import Message
from bot.client import app
from config import ADMIN_ID


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client, message: Message):
    await message.reply_text(
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ **AZ STREAM BOT**\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👋 Welcome! Send me any TeraBox link, and I will upload the file directly here.\n\n"
        "⚡ Instant VPS Download\n"
        "🚫 No Ads\n"
        "♾ Unlimited Speed\n\n"
        "Powered by AZ Network"
    )


@app.on_message(filters.command("myid") & filters.private)
async def myid_command(client, message: Message):
    await message.reply_text(f"🆔 Your Telegram User ID: `{message.from_user.id}`")
