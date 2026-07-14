"""
AZ TeraBox Bot - Main Entry Point
----------------------------------
Run this file to start the bot:
    python main.py
"""

import bot  # Registers all handlers via bot/__init__.py
from bot.client import app
from bot.utils.terabox import check_ndus_cookie

if __name__ == "__main__":
    print("🚀 Starting AZ TeraBox Bot...")
    check_ndus_cookie()
    app.run()
