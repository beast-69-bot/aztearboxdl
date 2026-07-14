"""
AZ TeraBox Bot - Main Entry Point
----------------------------------
Run this file to start the bot:
    python main.py
"""

import bot  # Registers all handlers via bot/__init__.py
from bot.client import app

if __name__ == "__main__":
    print("🚀 Starting AZ TeraBox Bot...")
    app.run()
