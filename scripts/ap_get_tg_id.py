"""
get_telegram_id.py — quick script to find your Telegram ID.
Run this, then send any message to your bot, and your ID will print.

Usage:
  python get_telegram_id.py
"""

import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()


async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    print(f"\n✅ Your Telegram ID: {user.id}")
    print(f"   Name: {user.first_name} {user.last_name or ''}")
    print(f"   Username: @{user.username or 'none'}")
    print(f"\nAdd to .env:  MIKHAIL_TELEGRAM_ID={user.id}")
    await update.message.reply_text(f"Your Telegram ID: {user.id}")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        return

    print("Send any message to your bot in Telegram...")
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle))
    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()
