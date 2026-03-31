"""
test_bot.py — quick smoke test to verify all components work before deploying.

Usage:
  python test_bot.py
"""

import os
import json
import base64
import asyncio
from dotenv import load_dotenv

load_dotenv()


def check_env():
    print("1. Checking environment variables...")
    required = [
        "TELEGRAM_BOT_TOKEN",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT",
        "ADMIN_SHEETS_ID",
        "MIKHAIL_TELEGRAM_ID",
    ]
    ok = True
    for key in required:
        val = os.environ.get(key, "")
        if val:
            print(f"   ✓ {key}")
        else:
            print(f"   ✗ {key} — MISSING")
            ok = False
    return ok


def check_google_creds():
    print("\n2. Checking Google service account...")
    try:
        raw = os.environ["GOOGLE_SERVICE_ACCOUNT"]
        creds = json.loads(base64.b64decode(raw))
        print(f"   ✓ Project: {creds.get('project_id')}")
        print(f"   ✓ Email:   {creds.get('client_email')}")
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def check_sheets():
    print("\n3. Checking Admin Google Sheets connection...")
    try:
        from sheets import get_sheets_client, AdminSheets
        gc = get_sheets_client()
        admin = AdminSheets(gc)
        config = admin.read_config()
        print(f"   ✓ Connected to Admin sheet")
        print(f"   ✓ Config rows: {len(config)}")
        envelopes = admin.get_envelopes()
        print(f"   ✓ Envelopes registered: {len(envelopes)}")
        for e in envelopes:
            print(f"      — {e.get('ID')}: {e.get('Name')}")
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def check_anthropic():
    print("\n4. Checking Anthropic API...")
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        print(f"   ✓ Anthropic API: OK")
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def check_openai():
    print("\n5. Checking OpenAI API (Whisper)...")
    try:
        import openai
        client = openai.OpenAI()
        models = client.models.list()
        has_whisper = any("whisper" in m.id for m in models.data)
        if has_whisper:
            print(f"   ✓ OpenAI API: OK, Whisper available")
        else:
            print(f"   ⚠ OpenAI API: OK but whisper-1 not found")
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def check_telegram():
    print("\n6. Checking Telegram bot token...")
    try:
        import asyncio
        from telegram import Bot
        async def _check():
            bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
            info = await bot.get_me()
            print(f"   ✓ Bot: @{info.username} ({info.first_name})")
        asyncio.run(_check())
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def main():
    print("=== Apolio Home — System Check ===\n")

    results = [
        check_env(),
        check_google_creds(),
        check_sheets(),
        check_anthropic(),
        check_openai(),
        check_telegram(),
    ]

    print("\n" + "=" * 40)
    if all(results):
        print("✅ All checks passed — ready to run: python bot.py")
    else:
        failed = sum(1 for r in results if not r)
        print(f"⚠️  {failed} check(s) failed — fix issues above before running bot.py")


if __name__ == "__main__":
    main()
