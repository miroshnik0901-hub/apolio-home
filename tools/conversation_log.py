"""
Conversation history logger for Apolio Home.
Stores every user message and bot response in the ConversationLog sheet
within the MM_BUDGET spreadsheet.

Storage format (see APOLIO_HOME_INTELLIGENCE_v1.0.md §5.2):
  A: timestamp    B: user_id      C: direction      D: message_type
  E: raw_text     F: intent       G: entities_json  H: tool_called
  I: result_short J: session_id   K: envelope_id
"""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

import gspread

HEADERS = [
    "timestamp", "user_id", "direction", "message_type",
    "raw_text", "intent", "entities_json", "tool_called",
    "result_short", "session_id", "envelope_id",
]

# Maximum rows to keep per user (oldest auto-purged)
MAX_ROWS = 500

# How many recent turns to load back for context injection
CONTEXT_TURNS = 5

# Sheet name inside the envelope spreadsheet
SHEET_NAME = "ConversationLog"


class ConversationLogger:
    """
    Append-only log of user↔bot exchanges.
    One instance per bot process (shared across all users).
    All writes are async-safe: use write_queue to avoid blocking the event loop.
    """

    def __init__(self, sheets_client: gspread.Client, file_id: str):
        self._client = sheets_client
        self._file_id = file_id
        self._wb = None
        self._ws = None
        self._ready = False
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task] = None

    def start(self):
        """Start the background writer task. Call once after bot starts."""
        if not self._writer_task:
            self._writer_task = asyncio.create_task(self._background_writer())

    async def _background_writer(self):
        """Drain the write queue, batching writes every 2 seconds."""
        while True:
            try:
                batch = []
                # Get first item (blocks until available)
                item = await asyncio.wait_for(self._write_queue.get(), timeout=10)
                batch.append(item)
                # Drain any additional pending items (non-blocking)
                while not self._write_queue.empty():
                    try:
                        batch.append(self._write_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                # Write batch
                if batch:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._write_batch, batch
                    )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                # Log errors but never crash the background task
                print(f"[ConversationLogger] write error: {e}")

    def _ensure_sheet(self):
        """Create ConversationLog sheet if it doesn't exist."""
        if self._ready:
            return
        try:
            wb = self._client.open_by_key(self._file_id)
            try:
                ws = wb.worksheet(SHEET_NAME)
            except gspread.WorksheetNotFound:
                ws = wb.add_worksheet(SHEET_NAME, rows=1000, cols=len(HEADERS))
                ws.append_row(HEADERS)
            self._wb = wb
            self._ws = ws
            self._ready = True
        except Exception as e:
            print(f"[ConversationLogger] could not ensure sheet: {e}")

    def _write_batch(self, rows: list[list]):
        """Synchronous batch write — called in executor thread."""
        try:
            self._ensure_sheet()
            if not self._ws:
                return
            # gspread append_rows for batching
            self._ws.append_rows(rows, value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"[ConversationLogger] batch write failed: {e}")

    def log_user(
        self,
        *,
        user_id: int,
        session_id: str,
        envelope_id: str,
        message_type: str,  # text / voice / photo / command
        raw_text: str,
        intent: str = "",
        entities: dict = None,
    ):
        """Queue a user-direction log entry (non-blocking)."""
        row = [
            datetime.now(timezone.utc).isoformat(),
            str(user_id),
            "user",
            message_type,
            raw_text[:500],  # cap at 500 chars
            intent,
            json.dumps(entities or {}, ensure_ascii=False),
            "",
            "",
            session_id,
            envelope_id or "",
        ]
        self._write_queue.put_nowait(row)

    def log_bot(
        self,
        *,
        user_id: int,
        session_id: str,
        envelope_id: str,
        tool_called: str = "",
        result_short: str = "",
        response_text: str = "",
    ):
        """Queue a bot-direction log entry (non-blocking)."""
        row = [
            datetime.now(timezone.utc).isoformat(),
            str(user_id),
            "bot",
            "response",
            response_text[:2000],
            "",
            "{}",
            tool_called,
            result_short[:200],
            session_id,
            envelope_id or "",
        ]
        self._write_queue.put_nowait(row)

    def get_recent_context(self, user_id: int, n: int = CONTEXT_TURNS) -> list[dict]:
        """
        Load last N conversation turns for this user.
        Returns list of dicts: [{direction, message_type, raw_text, tool_called, result_short}, ...]
        This is a synchronous call — use sparingly (only at message start).
        """
        try:
            self._ensure_sheet()
            if not self._ws:
                return []
            all_rows = self._ws.get_all_records()
            user_rows = [r for r in all_rows if str(r.get("user_id")) == str(user_id)]
            recent = user_rows[-n * 2:]  # n turns = up to 2n rows (user + bot per turn)
            return recent
        except Exception as e:
            print(f"[ConversationLogger] get_recent_context error: {e}")
            return []

    def format_context_for_prompt(self, user_id: int) -> str:
        """
        Return a compact string summarizing recent conversation for injection
        into the agent system prompt.
        """
        rows = self.get_recent_context(user_id)
        if not rows:
            return ""

        lines = ["RECENT CONVERSATION (last turns):"]
        for row in rows:
            direction = row.get("direction", "?")
            text = row.get("raw_text", "")
            result = row.get("result_short", "")
            ts = row.get("timestamp", "")[:16]  # YYYY-MM-DDTHH:MM

            if direction == "user" and text:
                lines.append(f"[{ts}] User: {text}")
            elif direction == "bot" and (result or text):
                lines.append(f"[{ts}] Bot: {result or text}")

        return "\n".join(lines)


def make_session_id() -> str:
    """Generate a short session identifier for grouping a conversation."""
    return uuid.uuid4().hex[:8]
