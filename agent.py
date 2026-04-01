"""
Apolio Home — AI Agent v2.0 (Intelligence Architecture)
Claude claude-sonnet-4-20250514 with tool use + enriched context.
System prompt loaded from ApolioHome_Prompt.md, augmented at runtime with:
  - budget snapshot (intelligence.py)
  - user goals (user_context.py)
  - conversation history (tools/conversation_log.py)
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import anthropic

from sheets import SheetsClient
from auth import AuthManager, SessionContext

logger = logging.getLogger(__name__)

_MM_BUDGET_FILE_ID = os.environ.get(
    "MM_BUDGET_FILE_ID", "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"
)

# ── Tools schema ───────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "add_transaction",
        "description": (
            "Record a new expense, income, or transfer. "
            "Defaults: expense, today, EUR, envelope = user's current envelope."
        ),
        "input_schema": {
            "type": "object",
            "required": ["amount"],
            "properties": {
                "amount":       {"type": "number"},
                "currency":     {"type": "string", "default": "EUR"},
                "date":         {"type": "string", "description": "YYYY-MM-DD, default today"},
                "envelope_id":  {"type": "string", "description": "Envelope ID, default current"},
                "category":     {"type": "string"},
                "subcategory":  {"type": "string"},
                "who":          {"type": "string", "enum": ["Mikhail", "Marina", "Joint"],
                                 "default": "Mikhail"},
                "account":      {"type": "string"},
                "type":         {"type": "string",
                                 "enum": ["expense", "income", "transfer"],
                                 "default": "expense"},
                "note":         {"type": "string"},
            },
        },
    },
    {
        "name": "edit_transaction",
        "description": "Edit a single field of an existing transaction by ID.",
        "input_schema": {
            "type": "object",
            "required": ["tx_id", "field", "new_value"],
            "properties": {
                "tx_id":     {"type": "string"},
                "field":     {"type": "string"},
                "new_value": {"type": "string"},
            },
        },
    },
    {
        "name": "delete_transaction",
        "description": (
            "Soft-delete a single transaction by tx_id (marks Deleted=TRUE, row stays in sheet). "
            "ALWAYS ask the user for confirmation before calling with confirmed=True. "
            "Show the transaction details and warn that this cannot be undone easily. "
            "Only pass confirmed=True after explicit user approval."
        ),
        "input_schema": {
            "type": "object",
            "required": ["tx_id"],
            "properties": {
                "tx_id":     {"type": "string"},
                "confirmed": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "delete_transaction_rows",
        "description": (
            "Physically and permanently delete a range of rows from the Transactions sheet "
            "by Google Sheet row number (row 1 = header, data rows start at 2). "
            "Use when user says 'удали строки N-M', 'delete rows N to M', 'remove row N'. "
            "TWO-STEP MANDATORY FLOW: "
            "(1) Always call first WITHOUT confirmed to get a preview of what will be deleted. "
            "(2) Show the preview to the user with a clear warning that this is IRREVERSIBLE. "
            "(3) Only call again with confirmed=True AFTER the user explicitly confirms "
            "(says 'да', 'yes', 'подтвердить', 'confirm', etc.). "
            "If user says 'нет', 'отмена', 'cancel' — do NOT call with confirmed=True. "
            "NEVER skip the preview step. NEVER call with confirmed=True on the first call."
        ),
        "input_schema": {
            "type": "object",
            "required": ["start_row", "end_row"],
            "properties": {
                "start_row":   {"type": "integer",
                                "description": "First row to delete (1-based, must be >= 2)"},
                "end_row":     {"type": "integer",
                                "description": "Last row to delete (inclusive)"},
                "confirmed":   {"type": "boolean",
                                "description": "false (default) = preview only; true = execute deletion"},
                "envelope_id": {"type": "string"},
            },
        },
    },
    {
        "name": "find_transactions",
        "description": "Search transactions by filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id":   {"type": "string"},
                "date_from":     {"type": "string"},
                "date_to":       {"type": "string"},
                "category":      {"type": "string"},
                "who":           {"type": "string"},
                "amount_min":    {"type": "number"},
                "amount_max":    {"type": "number"},
                "note_contains": {"type": "string"},
                "limit":         {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_summary",
        "description": "Aggregated budget summary for a period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id":  {"type": "string"},
                "period":       {"type": "string",
                                 "description": "YYYY-MM, 'current', or 'last'",
                                 "default": "current"},
                "breakdown_by": {"type": "string",
                                 "enum": ["category", "who", "account", "week"],
                                 "default": "category"},
            },
        },
    },
    {
        "name": "get_budget_status",
        "description": "Current month snapshot: contributed, spent, remaining, % used.",
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string"},
            },
        },
    },
    {
        "name": "import_wise_csv",
        "description": "Parse and import transactions from a Wise CSV export.",
        "input_schema": {
            "type": "object",
            "required": ["file_content", "envelope_id"],
            "properties": {
                "file_content": {"type": "string"},
                "envelope_id":  {"type": "string"},
            },
        },
    },
    {
        "name": "set_fx_rate",
        "description": "Set ECB exchange rate for a month and currency. Admin only.",
        "input_schema": {
            "type": "object",
            "required": ["month", "currency", "rate"],
            "properties": {
                "month":    {"type": "string", "description": "YYYY-MM"},
                "currency": {"type": "string"},
                "rate":     {"type": "number",
                             "description": "Units per 1 EUR, e.g. PLN: 4.27"},
            },
        },
    },
    {
        "name": "update_config",
        "description": "Update a bot config value. Admin only.",
        "input_schema": {
            "type": "object",
            "required": ["key", "value"],
            "properties": {
                "key":   {"type": "string"},
                "value": {"type": "string"},
            },
        },
    },
    {
        "name": "add_authorized_user",
        "description": "Grant Telegram user access to the bot. Admin only.",
        "input_schema": {
            "type": "object",
            "required": ["telegram_id", "role"],
            "properties": {
                "telegram_id": {"type": "integer"},
                "name":        {"type": "string"},
                "role":        {"type": "string",
                                "enum": ["admin", "contributor", "readonly"]},
                "envelopes":   {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "remove_authorized_user",
        "description": "Revoke bot access. Admin only.",
        "input_schema": {
            "type": "object",
            "required": ["telegram_id"],
            "properties": {
                "telegram_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "list_envelopes",
        "description": (
            "List all active budget envelopes with their names, IDs, monthly caps, "
            "and Google Sheets links. Use this when the user asks to see envelopes, "
            "files, or wants to know what budgets are available."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_envelope",
        "description": (
            "Create a new budget envelope: Google Sheets file + register in Admin. "
            "Admin only."
        ),
        "input_schema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name":          {"type": "string"},
                "currency":      {"type": "string", "default": "EUR"},
                "monthly_cap":   {"type": "number"},
                "split_rule":    {"type": "string",
                                  "enum": ["solo", "50/50", "custom"],
                                  "default": "solo"},
                "owner_id":      {"type": "integer"},
                "viewer_ids":    {"type": "array", "items": {"type": "integer"}},
            },
        },
    },
    # ── Intelligence tools (v2.0) ─────────────────────────────────────────
    {
        "name": "save_goal",
        "description": (
            "Save a financial goal for the user. Examples: monthly savings target, "
            "emergency fund target, custom goal. Use when user expresses a financial "
            "goal or target. key must be one of: savings_target_monthly, "
            "emergency_fund_target, emergency_fund_current, custom_goal."
        ),
        "input_schema": {
            "type": "object",
            "required": ["key", "value"],
            "properties": {
                "key":   {"type": "string",
                          "enum": ["savings_target_monthly", "emergency_fund_target",
                                   "emergency_fund_current", "custom_goal"]},
                "value": {"type": "string", "description": "The goal value, e.g. '500' for 500 EUR/month"},
            },
        },
    },
    {
        "name": "get_intelligence",
        "description": (
            "Get an intelligence analysis: category trends vs last month, "
            "anomalies (categories significantly above average), budget pace forecast, "
            "and large recent transactions. Use when user asks for analysis, trends, "
            "recommendations, or 'what should I do?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string"},
            },
        },
    },
]

# ── System prompt loader ───────────────────────────────────────────────────────

FALLBACK_PROMPT = """You are Apolio Home, a family budget assistant for Mikhail Miro.
Always respond. Never stay silent. Handle RU/UK/EN/IT mixed input naturally.
Current date: {today}. User: {user_name} (role: {role}). Active envelope: {envelope_id}.
Add transactions proactively from natural language. Respond in the user's language.

{intelligence_context}
{goals_context}
{conversation_context}
"""


def _load_system_prompt() -> str:
    """Load agent system prompt from ApolioHome_Prompt.md.
    Strips the YAML-style header block (everything before the second ---).
    Falls back to minimal inline prompt if file not found."""
    prompt_file = Path(__file__).parent / "ApolioHome_Prompt.md"
    try:
        raw = prompt_file.read_text(encoding="utf-8")
        lines = raw.split("\n")
        start = 0
        dashes = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                dashes += 1
                if dashes == 2:  # second --- ends the header block
                    start = i + 1
                    break
        template = "\n".join(lines[start:]).strip()
        # Append intelligence context placeholders if not present
        if "{intelligence_context}" not in template:
            template += "\n\n---\n\n{intelligence_context}\n\n{goals_context}\n\n{conversation_context}"
        return template
    except Exception as e:
        logger.warning(f"Could not load ApolioHome_Prompt.md: {e}. Using fallback prompt.")
        return FALLBACK_PROMPT


# Load once at module startup
_SYSTEM_PROMPT_TEMPLATE = _load_system_prompt()


# ── Intelligence helpers (lazy-loaded singletons) ─────────────────────────────

_intelligence_engine = None
_user_context_mgr = None
_conv_logger = None


def _get_intelligence_engine(sheets: SheetsClient):
    global _intelligence_engine
    if _intelligence_engine is None:
        from intelligence import IntelligenceEngine
        _intelligence_engine = IntelligenceEngine(sheets)
    return _intelligence_engine


def _get_user_context_mgr(sheets: SheetsClient):
    global _user_context_mgr
    if _user_context_mgr is None:
        from user_context import UserContextManager
        _user_context_mgr = UserContextManager(sheets._gc, _MM_BUDGET_FILE_ID)
    return _user_context_mgr


def _get_conv_logger():
    """Try to get the conversation logger from bot.py (shared instance)."""
    global _conv_logger
    if _conv_logger is not None:
        return _conv_logger
    try:
        import bot as _bot_module
        _conv_logger = getattr(_bot_module, "conv_log", None)
    except Exception:
        pass
    return _conv_logger


# ── Agent ──────────────────────────────────────────────────────────────────────

class ApolioAgent:
    def __init__(self, sheets: SheetsClient, auth: AuthManager):
        self.sheets = sheets
        self.auth = auth
        self.client = anthropic.AsyncAnthropic()

    async def _build_context(self, session: SessionContext) -> dict:
        """
        Pre-compute intelligence snapshot, goals, and conversation history.
        Returns dict of context blocks for system prompt injection.
        All errors are swallowed — context enrichment must never crash the agent.
        """
        import db as appdb

        intelligence_text = ""
        goals_text = ""
        conversation_text = ""

        envelope_id = session.current_envelope_id or "MM_BUDGET"

        # 1. Intelligence snapshot (budget status, trends, anomalies)
        try:
            engine = _get_intelligence_engine(self.sheets)
            from intelligence import format_snapshot_for_prompt
            snap = engine.compute_snapshot(envelope_id)
            if not snap.get("error"):
                intelligence_text = format_snapshot_for_prompt(snap)
        except Exception as e:
            logger.warning(f"Intelligence context failed: {e}")

        # 2. User goals — PostgreSQL first, Google Sheets fallback
        try:
            if appdb.is_ready():
                ctx = await appdb.ctx_get_all(session.user_id)
                from user_context import format_goals_for_prompt
                goals_text = format_goals_for_prompt(ctx)
            else:
                mgr = _get_user_context_mgr(self.sheets)
                from user_context import format_goals_for_prompt
                ctx = mgr.get_all(session.user_id)
                goals_text = format_goals_for_prompt(ctx)
        except Exception as e:
            logger.warning(f"User context failed: {e}")

        # 3. Conversation history — PostgreSQL (primary)
        try:
            if appdb.is_ready():
                rows = await appdb.get_recent_context(session.user_id, n=10)
                conversation_text = appdb.format_context_for_prompt(rows)
            else:
                # Fallback: old ConversationLogger (Google Sheets)
                conv = _get_conv_logger()
                if conv:
                    conversation_text = conv.format_context_for_prompt(session.user_id)
        except Exception as e:
            logger.warning(f"Conversation context failed: {e}")

        return {
            "intelligence_context": intelligence_text,
            "goals_context": goals_text,
            "conversation_context": conversation_text,
        }

    async def run(self, message: str, session: SessionContext,
                  media_type: str = "text",
                  media_data: bytes | None = None) -> str:
        """
        Run the agent with a user message.
        Returns the bot's text response. Never returns empty string.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Build enriched context (async — loads PostgreSQL history + intelligence)
        context = await self._build_context(session)

        system = _SYSTEM_PROMPT_TEMPLATE.format(
            today=today,
            user_name=session.user_name,
            role=session.role,
            envelope_id=session.current_envelope_id or "MM_BUDGET",
            intelligence_context=context.get("intelligence_context", ""),
            goals_context=context.get("goals_context", ""),
            conversation_context=context.get("conversation_context", ""),
        )

        # Build user content (text or with media)
        if media_type == "photo" and media_data:
            import base64
            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(media_data).decode(),
                    },
                },
                {"type": "text", "text": message or "Extract transaction data from this receipt."},
            ]
        else:
            user_content = message

        messages = [{"role": "user", "content": user_content}]

        # Agentic loop
        max_iterations = 5
        last_text = ""

        for iteration in range(max_iterations):
            response = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                # Extract text blocks — never return empty
                text_blocks = [
                    b.text for b in response.content
                    if hasattr(b, "text") and b.text.strip()
                ]
                if text_blocks:
                    return "\n".join(text_blocks)
                # Claude finished without text — use last seen text or ask for summary
                if last_text:
                    return last_text
                # Generate a one-line summary
                break  # fall through to fallback

            if response.stop_reason == "tool_use":
                # Collect any text Claude wrote alongside the tool call
                for block in response.content:
                    if hasattr(block, "text") and block.text.strip():
                        last_text = block.text.strip()

                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await self._execute_tool(block.name, block.input, session)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                messages.append({"role": "user", "content": tool_results})

        # Fallback: ask Claude for a short plain-text summary of what happened
        try:
            fallback = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                system=system,
                messages=messages + [{
                    "role": "user",
                    "content": "Кратко (1-2 предложения) опиши что ты только что сделал, на языке пользователя.",
                }],
            )
            for block in fallback.content:
                if hasattr(block, "text") and block.text.strip():
                    return block.text.strip()
        except Exception as e:
            logger.error(f"Fallback response failed: {e}")

        return last_text or "✓"

    async def _execute_tool(self, name: str, params: dict,
                             session: SessionContext) -> Any:
        """Dispatch tool call to the appropriate handler."""
        from tools.transactions import (
            tool_add_transaction, tool_edit_transaction,
            tool_delete_transaction, tool_delete_transaction_rows,
            tool_find_transactions,
        )
        from tools.summary import tool_get_summary, tool_get_budget_status
        from tools.wise import tool_import_wise_csv
        from tools.fx import tool_set_fx_rate
        from tools.config_tools import (
            tool_update_config, tool_add_authorized_user,
            tool_remove_authorized_user,
        )
        from tools.envelope_tools import tool_create_envelope, tool_list_envelopes

        dispatch = {
            "list_envelopes":         tool_list_envelopes,
            "add_transaction":        tool_add_transaction,
            "edit_transaction":       tool_edit_transaction,
            "delete_transaction":     tool_delete_transaction,
            "delete_transaction_rows": tool_delete_transaction_rows,
            "find_transactions":      tool_find_transactions,
            "get_summary":            tool_get_summary,
            "get_budget_status":      tool_get_budget_status,
            "import_wise_csv":        tool_import_wise_csv,
            "set_fx_rate":            tool_set_fx_rate,
            "update_config":          tool_update_config,
            "add_authorized_user":    tool_add_authorized_user,
            "remove_authorized_user": tool_remove_authorized_user,
            "create_envelope":        tool_create_envelope,
            # Intelligence tools (v2.0)
            "save_goal":              self._tool_save_goal,
            "get_intelligence":       self._tool_get_intelligence,
        }

        handler = dispatch.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            result = await handler(params, session, self.sheets, self.auth)
            # Write audit log for state-changing operations
            if name not in ("find_transactions", "get_summary", "get_budget_status",
                            "list_envelopes", "get_intelligence"):
                self.sheets.write_audit(
                    session.user_id, session.user_name,
                    name, session.current_envelope_id,
                    json.dumps(params)[:200]
                )
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return {"error": str(e)}

    # ── Intelligence tool handlers ────────────────────────────────────────

    async def _tool_save_goal(self, params: dict, session: SessionContext,
                               sheets: SheetsClient, auth: AuthManager) -> Any:
        """Save a financial goal for the user."""
        key = params.get("key", "")
        value = params.get("value", "")
        if not key or not value:
            return {"error": "key and value are required"}

        try:
            mgr = _get_user_context_mgr(sheets)
            mgr.set(session.user_id, key, value)
            return {
                "status": "ok",
                "message": f"Goal saved: {key} = {value}",
            }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_get_intelligence(self, params: dict, session: SessionContext,
                                      sheets: SheetsClient, auth: AuthManager) -> Any:
        """Run intelligence analysis and return structured results."""
        envelope_id = params.get("envelope_id") or session.current_envelope_id or "MM_BUDGET"

        try:
            engine = _get_intelligence_engine(sheets)
            snap = engine.compute_snapshot(envelope_id)
            return snap
        except Exception as e:
            return {"error": str(e)}
