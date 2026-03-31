
---

## TASK 10 — AI Conversation: Make Bot "Alive" (CRITICAL)

**Problem:** Bot currently ignores many messages because the system prompt is too short
and rule-based. Claude doesn't know what to do with unclear input → stays silent.
This is unacceptable for daily use.

**Root cause in current `agent.py`:**
The SYSTEM_PROMPT has minimal behavior rules. Claude falls back to "I don't know
what tool to call" → returns empty text → bot sends nothing.

### 10a. Load system prompt from ApolioHome_Prompt.md

Replace the hardcoded SYSTEM_PROMPT string in `agent.py` with a loader that reads
`ApolioHome_Prompt.md` at startup:

```python
import os
from pathlib import Path

def _load_system_prompt() -> str:
    """Load agent system prompt from ApolioHome_Prompt.md.
    Falls back to minimal inline prompt if file not found."""
    prompt_file = Path(__file__).parent / "ApolioHome_Prompt.md"
    try:
        raw = prompt_file.read_text(encoding="utf-8")
        # Strip the header block (lines before second ---)
        lines = raw.split("\n")
        start = 0
        dashes = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                dashes += 1
                if dashes == 2:  # second --- ends the header
                    start = i + 1
                    break
        return "\n".join(lines[start:]).strip()
    except Exception as e:
        logger.warning(f"Could not load ApolioHome_Prompt.md: {e}. Using fallback prompt.")
        return FALLBACK_PROMPT

FALLBACK_PROMPT = """You are Apolio Home, a family budget assistant.
Always respond. Never stay silent. Handle RU/UK/EN/IT mixed input.
Current date: {today}. User: {user_name}. Envelope: {envelope_id}.
"""

# Load once at module startup
_SYSTEM_PROMPT_TEMPLATE = _load_system_prompt()
```

Then in `ApolioAgent.run()`, replace:
```python
system = SYSTEM_PROMPT.format(...)
```
with:
```python
system = _SYSTEM_PROMPT_TEMPLATE.format(
    today=today,
    user_name=session.user_name,
    role=session.role,
    envelope_id=session.current_envelope_id or "MM_BUDGET",
)
```

Also delete `AGENT_PROMPT.md` — it is deprecated and replaced by `ApolioHome_Prompt.md`.

### 10b. Fix "bot stays silent" — ensure agent always returns text

In `ApolioAgent.run()`, the loop currently returns `"Processing complete."` if
max iterations reached, and `"Done."` if no text block found. These are not user-facing.

Fix the return logic:

```python
# After the tool-use loop
# If we get here without a text response, ask Claude for a plain text summary
fallback_response = self.client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=256,
    system=system,
    messages=messages + [{
        "role": "user",
        "content": "Summarize what you just did in one short sentence in the user's language."
    }],
)
for block in fallback_response.content:
    if hasattr(block, "text") and block.text.strip():
        return block.text.strip()

return "✓"  # absolute last resort
```

Also fix the `end_turn` response extractor to handle cases where Claude's response
has tool_use blocks but no text block (this causes silent responses):

```python
if response.stop_reason == "end_turn":
    text_blocks = [b.text for b in response.content if hasattr(b, "text") and b.text.strip()]
    if text_blocks:
        return "\n".join(text_blocks)
    # Claude used tools but wrote no summary — generate one
    continue  # let the loop handle it, don't return empty
```

### 10c. Handle non-budget messages explicitly

Add a special case in `handle_message` in `bot.py` for very short messages
that look like greetings (no numbers, no verbs related to spending):

```python
GREETINGS = {"привет", "hi", "hello", "ciao", "hey", "добрий день",
             "как дела", "что умеешь", "help", "start", "хелп"}

if text.lower().strip() in GREETINGS:
    # Don't call agent for greetings — respond directly
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Просто напишите что потратили:\n"
        "«кофе 3.50» или «продукты 85 EUR»\n\n"
        "Или нажмите кнопку ниже 👇",
        reply_markup=MAIN_KEYBOARD,
    )
    return
```

This prevents unnecessary Claude API calls for simple greetings and ensures
immediate response.

### 10d. Add typing indicator before ALL agent calls

Currently `send_chat_action("typing")` is called in `handle_message`.
Verify it's called BEFORE the agent, not after. Add a timeout: if agent takes > 8s,
send typing again:

```python
await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

# For long operations, keep typing indicator alive
async def keep_typing():
    for _ in range(10):  # max 80 seconds
        await asyncio.sleep(8)
        try:
            await ctx.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )
        except Exception:
            break

typing_task = asyncio.create_task(keep_typing())
try:
    response = await agent.run(text, session, ...)
finally:
    typing_task.cancel()
```

### 10e. Increase Claude max_tokens for richer responses

Current `max_tokens=1024` is too low for a report that includes multiple categories
with bars. Increase to 2048 in `agent.py`:

```python
response = self.client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2048,  # was 1024
    ...
)
```

### 10f. Test specifically for "silent bot" scenarios

Add to Task 8 test sequence:
- Send "привет" → should get friendly greeting immediately (no API call)
- Send "45" → should ask "45 EUR — на что?"
- Send "как дела?" → should respond naturally and offer to show budget
- Send "что ты умеешь?" → should explain capabilities
- Send "кофе" (no amount) → should ask "Сколько стоило?"
- Send a long voice message in Ukrainian → should transcribe + process correctly
- Send "покажи последние 3 записи" → should show recent transactions
- Send "сравни этот месяц с прошлым" → should show both months

---

## UPDATED: Files to modify

- `auth.py` — Tasks 1, 5d
- `bot.py` — Tasks 2, 6a, 6b, 6c, 6d, 6e, 10c, 10d
- `agent.py` — Tasks 7a, 7b, 10a, 10b, 10e
- `sheets.py` — Tasks 7c, 4a (column order constant)
- `tools/transactions.py` — Task 4a (new column order in row list)
- `tools/summary.py` — no changes needed
- `tools/envelope_tools.py` — Task 7a (Polina routing)
- `reports.py` — Task 6b, 7d (new file, create it)
- `ApolioHome_Prompt.md` — Task 10 (behavior spec, loaded by agent.py — do NOT modify content)
- `requirements.txt` — add pytz
- `SETUP_REPORT.md` — Task 9

## Files to DELETE
- `AGENT_PROMPT.md` — deprecated, replaced by ApolioHome_Prompt.md

## Files to NOT modify
- `tools/wise.py`
- `tools/fx.py`
- `tools/config_tools.py`
- `setup_admin.py`
- `test_bot.py`
- `encode_service_account.py`
- `get_telegram_id.py`
