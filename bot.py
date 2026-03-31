"""Apolio Home — Telegram Bot Entry Point"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Logging: console + rotating file
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
from logging.handlers import RotatingFileHandler
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "bot.log"),
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger(__name__)

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from sheets import SheetsClient
from auth import AuthManager, get_session
from agent import ApolioAgent

# Initialise shared clients
sheets = SheetsClient()
auth = AuthManager(sheets)
agent = ApolioAgent(sheets, auth)


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_user = auth.get_user(user.id)

    if not tg_user:
        await update.message.reply_text("Access denied.")
        return

    session = get_session(user.id, user.first_name, tg_user["role"])

    # Route by message type
    msg = update.message

    if msg.text:
        text = msg.text
        media_type = "text"
        media_data = None

    elif msg.voice or msg.audio:
        # Transcribe via Whisper
        file_obj = await (msg.voice or msg.audio).get_file()
        audio_bytes = await file_obj.download_as_bytearray()
        text = await transcribe_audio(bytes(audio_bytes))
        media_type = "text"
        media_data = None

    elif msg.photo:
        # Get highest-resolution photo
        file_obj = await msg.photo[-1].get_file()
        media_data = bytes(await file_obj.download_as_bytearray())
        text = msg.caption or ""
        media_type = "photo"

    elif msg.document and msg.document.mime_type in ("text/csv", "application/csv"):
        file_obj = await msg.document.get_file()
        csv_bytes = await file_obj.download_as_bytearray()
        text = f"[CSV import]\n{csv_bytes.decode('utf-8', errors='replace')}"
        media_type = "text"
        media_data = None

    else:
        await update.message.reply_text("Unsupported message type.")
        return

    response = await agent.run(
        text, session,
        media_type=media_type,
        media_data=media_data,
    )
    await update.message.reply_text(response)


async def transcribe_audio(audio_bytes: bytes) -> str:
    import openai, re
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.ogg", audio_bytes, "audio/ogg"),
        language=None,
    )
    text = transcript.text.strip().rstrip(".")
    return re.sub(r"\s+", " ", text)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Apolio Home — ready.\n"
        "Send me a message, voice note, or photo of a receipt."
    )


async def cmd_envelope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Set current envelope: /envelope MM_BUDGET"""
    user = update.effective_user
    tg_user = auth.get_user(user.id)
    if not tg_user:
        await update.message.reply_text("Access denied.")
        return
    if not ctx.args:
        envelopes = sheets.get_envelopes()
        names = [f"{e['ID']} — {e['Name']}" for e in envelopes if e.get('ID')]
        await update.message.reply_text(
            "Usage: /envelope <ID>\n\nAvailable:\n" + "\n".join(names) if names else "No envelopes registered."
        )
        return
    env_id = ctx.args[0].upper()
    envelopes = sheets.get_envelopes()
    match = next((e for e in envelopes if e.get("ID") == env_id), None)
    if not match:
        await update.message.reply_text(f"Envelope '{env_id}' not found.")
        return
    session = get_session(user.id, user.first_name, tg_user["role"])
    session.current_envelope_id = env_id
    await update.message.reply_text(f"✓ Active envelope: {match['Name']} ({env_id})")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("envelope", cmd_envelope))
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND, handle_message
    ))

    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            webhook_url=webhook_url,
        )
    else:
        # Local dev: polling
        app.run_polling()


if __name__ == "__main__":
    main()
