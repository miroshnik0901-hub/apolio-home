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

def _resolve_budget_file_id(sheets_client) -> str:
    """Get budget file_id from Admin → Envelopes (no hardcoded IDs)."""
    try:
        for e in sheets_client.get_envelopes():
            if e.get("ID") == "MM_BUDGET" and str(e.get("Active", "")).upper() == "TRUE":
                return e["file_id"]
    except Exception:
        pass
    return os.environ.get("MM_BUDGET_FILE_ID", "")

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
                "who":          {"type": "string",
                                 "description": "Who made the expense. Use values from get_reference_data."},
                "account":      {"type": "string",
                                 "description": "Payment account/card. Use values from get_reference_data."},
                "type":         {"type": "string",
                                 "enum": ["expense", "income", "transfer"],
                                 "default": "expense"},
                "note":         {"type": "string"},
                "force_new":    {"type": "boolean",
                                 "description": "Set true to bypass validation and allow new category/who/account values not yet in the reference lists."},
                "force_add":    {"type": "boolean",
                                 "description": "Set true to bypass duplicate detection and add the transaction even if a similar one exists on the same date."},
            },
        },
    },
    {
        "name": "get_reference_data",
        "description": (
            "Fetch the reference lists for the current envelope: "
            "known categories, subcategories, accounts, users (who), and currencies. "
            "Call this when: (1) user asks 'what categories do we have?', "
            "(2) add_transaction returns unknown_values status, "
            "(3) you're unsure whether a category/who value is valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string", "description": "Envelope ID, default current"},
            },
        },
    },
    {
        "name": "save_learning",
        "description": (
            "Record a learning event to improve future interpretations. "
            "Call this when: (1) user CORRECTS something you interpreted wrong, "
            "(2) user CONFIRMS your interpretation (3+ confirmations = use automatically), "
            "(3) user approves a NEW category/user/account via force_new, "
            "(4) you identify a recurring PATTERN in the user's transactions, "
            "(5) you resolved an AMBIGUITY and know the correct interpretation. "
            "Do NOT call for read-only queries or data lookups."
        ),
        "input_schema": {
            "type": "object",
            "required": ["event_type"],
            "properties": {
                "event_type": {
                    "type": "string",
                    "enum": ["vocabulary", "correction", "confirmation", "pattern",
                             "new_value", "ambiguity_resolved"],
                },
                "trigger": {
                    "type": "string",
                    "description": "The word/phrase that triggered this (e.g. 'шаурма', 'садик')",
                },
                "learned": {
                    "type": "object",
                    "description": "What was learned: {field, value, category, subcategory, who, ...}",
                },
                "confidence_delta": {
                    "type": "number",
                    "description": "+0.1 for confirmation, -0.3 for correction. Default 0.",
                },
                "original_input": {
                    "type": "string",
                    "description": "The user's original message that produced this event",
                },
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
        "name": "sort_transactions",
        "description": (
            "Sort all rows in the Transactions sheet by date. "
            "Use when user says 'отсортируй', 'sort', 'упорядочи по дате', "
            "'сначала старые', 'сначала новые', or after adding transactions for past dates. "
            "asc = oldest first (default); desc = newest first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order":       {"type": "string", "enum": ["asc", "desc"],
                                "description": "asc = oldest first; desc = newest first",
                                "default": "asc"},
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
    {
        "name": "search_history",
        "description": (
            "Search the conversation history for a user, going deeper than the last 10 messages. "
            "Use when the user references something said earlier that is not in the current context, "
            "or when you need to find a pattern, previous decision, past transaction mention, or "
            "any prior exchange. "
            "keyword is optional — omit to page through all history. "
            "Use offset to paginate: first call offset=0, next call offset=20, etc. "
            "Returns messages sorted oldest-first within the page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string",
                            "description": "Case-insensitive substring to search in message text; omit for all"},
                "limit":   {"type": "integer", "default": 20,
                            "description": "Max rows to return (max 50)"},
                "offset":  {"type": "integer", "default": 0,
                            "description": "Skip first N rows (for pagination)"},
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
    {
        "name": "get_contribution_status",
        "description": (
            "Show per-user contribution and expense split status for the current or given month. "
            "Use when user asks: 'кто сколько внёс?', 'сколько должна Marina?', "
            "'как распределились расходы?', 'покажи расчёт 50/50', 'contribution status', "
            "'settlement', 'кто в плюсе / минусе?'. "
            "Returns: total contributions per user, total expenses, threshold, "
            "each user's share of expenses, and balance (positive = credit, negative = owes)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string",
                                "description": "Envelope ID, default = current"},
                "month": {"type": "string",
                          "description": "YYYY-MM, default = current month"},
            },
        },
    },
    {
        "name": "refresh_dashboard",
        "description": (
            "Rewrite the Dashboard tab in the Google Sheet with current budget snapshot, "
            "per-user contribution table, category breakdown, and recent transactions. "
            "Use when user says: 'обнови дашборд', 'refresh dashboard', 'покажи дашборд в таблице', "
            "'запиши в таблицу', 'обнови Google Sheets'. "
            "Also call this automatically after add_transaction when the user mentions the dashboard."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string",
                                "description": "Envelope ID, default = current"},
                "month": {"type": "string",
                          "description": "YYYY-MM, default = current month"},
            },
        },
    },
    {
        "name": "save_receipt",
        "description": (
            "Save itemized receipt data after a photo transaction is confirmed and recorded. "
            "Call this after add_transaction succeeds for a photo/receipt message. "
            "Stores merchant, items, and AI summary to the Receipts tab."
        ),
        "input_schema": {
            "type": "object",
            "required": ["transaction_id", "total_amount"],
            "properties": {
                "transaction_id": {"type": "string"},
                "merchant":       {"type": "string", "default": ""},
                "date":           {"type": "string", "description": "YYYY-MM-DD"},
                "total_amount":   {"type": "number"},
                "currency":       {"type": "string", "default": "EUR"},
                "items":          {
                    "type": "array",
                    "description": "List of {name, amount, category}",
                    "items": {"type": "object"},
                },
                "ai_summary":     {"type": "string",
                                   "description": "One-line summary, e.g. 'Esselunga weekly shop, 12 items'"},
                "raw_text":       {"type": "string", "default": ""},
                "tg_file_id":     {"type": "string", "default": ""},
            },
        },
    },
    {
        "name": "refresh_learning_summary",
        "description": (
            "Write a human-readable summary of all learned vocabulary, patterns and corrections "
            "from the agent_learning PostgreSQL table to the 'Learning' tab in the Admin Google Sheet. "
            "Call when the user asks: 'покажи что ты выучил', 'обнови Learning', "
            "'refresh learning', 'what have you learned', 'запиши обучение в таблицу'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "envelope_id": {"type": "string", "description": "Filter by envelope, default = all"},
                "min_confidence": {"type": "number", "description": "Min confidence threshold 0.0–1.0, default 0.5"},
            },
        },
    },
    {
        "name": "update_dashboard_config",
        "description": (
            "Update a DashboardConfig setting in the Admin sheet. Use when user wants to change "
            "how the dashboard behaves: e.g. 'обновляй дашборд автоматически', "
            "'покажи историю за 6 месяцев', 'отключи историю взносов', "
            "'установи предупреждение при 75%'. "
            "Valid keys: auto_refresh_on_transaction (TRUE/FALSE), "
            "show_contribution_history (TRUE/FALSE), history_months (number), "
            "budget_warning_pct (number), show_category_breakdown (TRUE/FALSE), "
            "master_template_id (file_id), mode (prod/test), test_file_id (file_id)."
        ),
        "input_schema": {
            "type": "object",
            "required": ["key", "value"],
            "properties": {
                "key": {"type": "string", "description": "Config key to update"},
                "value": {"type": "string", "description": "New value"},
            },
        },
    },
    {
        "name": "present_options",
        "description": (
            "Attach inline choice buttons to your response. Call this tool BEFORE writing your "
            "response text whenever you need the user to confirm or choose from options. "
            "Common use cases: confirming a transaction ('Записать?'), "
            "choosing between suggestions ('Какую категорию использовать?'), "
            "yes/no confirmations before deleting, etc. "
            "Do NOT call for routine confirmations where no choice is needed."
        ),
        "input_schema": {
            "type": "object",
            "required": ["choices"],
            "properties": {
                "choices": {
                    "type": "array",
                    "description": "List of options to show as buttons",
                    "items": {
                        "type": "object",
                        "required": ["label", "value"],
                        "properties": {
                            "label": {"type": "string", "description": "Button text, e.g. '✅ Да, записать'"},
                            "value": {"type": "string", "description": "Short value passed back, e.g. 'yes', 'no', 'cat_food'"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "store_pending_receipt",
        "description": (
            "Save parsed receipt/photo data to session so it persists between messages. "
            "Call this IMMEDIATELY after analyzing a receipt photo, BEFORE present_options. "
            "When the user later confirms, the stored data is injected into your context "
            "so you can call add_transaction without asking again."
        ),
        "input_schema": {
            "type": "object",
            "required": ["merchant", "total_amount"],
            "properties": {
                "merchant": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "total_amount": {"type": "number"},
                "currency": {"type": "string", "default": "EUR"},
                "category": {"type": "string"},
                "subcategory": {"type": "string"},
                "who": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Parsed line items from receipt",
                },
                "ai_summary": {"type": "string"},
                "raw_text": {"type": "string", "description": "Raw OCR text from receipt"},
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
{contribution_context}
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
            template += (
                "\n\n---\n\n{learning_context}\n\n{intelligence_context}\n\n"
                "{goals_context}\n\n{contribution_context}\n\n{conversation_context}"
            )
        return template
    except Exception as e:
        logger.warning(f"Could not load ApolioHome_Prompt.md: {e}. Using fallback prompt.")
        return FALLBACK_PROMPT


# Load once at module startup
_SYSTEM_PROMPT_TEMPLATE = _load_system_prompt()


def _safe_format(template: str, **kwargs) -> str:
    """Replace known {placeholders} without crashing on literal {curly} braces in the text.
    Python's str.format() raises KeyError when the template contains patterns like
    {mapping: value} (from prompt examples). This helper does explicit key-by-key
    replacement so unrecognised patterns are left untouched."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


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
        _user_context_mgr = UserContextManager(sheets._gc, _resolve_budget_file_id(sheets))
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
        contribution_text = ""

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

        # NOTE: Conversation history is NOT injected here as text.
        # It is passed directly as a structured messages[] array in agent.run()
        # via get_recent_messages_for_api(). Injecting it twice (here + messages[])
        # wastes tokens and creates confusion. Keep it in messages[] only.

        # 3. Contribution & split status
        try:
            from intelligence import compute_contribution_status, format_contribution_for_prompt
            contrib_snap = compute_contribution_status(self.sheets, envelope_id)
            contribution_text = format_contribution_for_prompt(contrib_snap)
        except Exception as e:
            logger.warning(f"Contribution context failed: {e}")

        # 4. Self-learning context (vocabulary mappings + patterns)
        learning_text = ""
        try:
            if appdb.is_ready():
                learning_text = await appdb.get_learning_context_for_prompt(session.user_id)
        except Exception as e:
            logger.warning(f"Learning context failed: {e}")

        return {
            "intelligence_context": intelligence_text,
            "goals_context": goals_text,
            "conversation_context": "",   # intentionally blank — history is in messages[]
            "contribution_context": contribution_text,
            "learning_context": learning_text,
        }

    async def run(self, message: str, session: SessionContext,
                  media_type: str = "text",
                  media_data: bytes | None = None,
                  telegram_bot=None) -> str:
        """
        Run the agent with a user message.
        telegram_bot: optional Telegram Bot instance — when provided, photo messages
                      in conversation history are re-downloaded and included as images
                      so Claude has visual memory of previously sent screenshots.
        Returns the bot's text response. Never returns empty string.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Build enriched context (async — loads PostgreSQL history + intelligence)
        context = await self._build_context(session)

        # Map lang code to full language name for system prompt
        _lang_names = {"ru": "Russian", "uk": "Ukrainian", "en": "English", "it": "Italian"}
        user_lang = getattr(session, "lang", "ru") or "ru"
        lang_name = _lang_names.get(user_lang, "Russian")

        system = _safe_format(
            _SYSTEM_PROMPT_TEMPLATE,
            today=today,
            user_name=session.user_name,
            role=session.role,
            envelope_id=session.current_envelope_id or "MM_BUDGET",
            intelligence_context=context.get("intelligence_context", ""),
            goals_context=context.get("goals_context", ""),
            contribution_context=context.get("contribution_context", ""),
            conversation_context=context.get("conversation_context", ""),
            learning_context=context.get("learning_context", ""),
        )

        # T-066: Inject strict language directive so agent never switches language
        system += (
            f"\n\n---\n\n## MANDATORY LANGUAGE\n"
            f"The user's language is **{lang_name}** (code: {user_lang}). "
            f"You MUST respond in {lang_name}. Do NOT switch to another language "
            f"under any circumstances, even if the input looks like a callback value "
            f"or a single English word. Always {lang_name}."
        )

        # T-065/T-067: Inject pending receipt context so agent remembers photo analysis
        pending_receipt = getattr(session, "pending_receipt", None)
        if pending_receipt:
            system += (
                f"\n\n---\n\n## PENDING RECEIPT (awaiting user confirmation)\n"
                f"The user previously sent a receipt photo. You analyzed it and proposed a transaction.\n"
                f"Receipt data:\n"
                f"- Merchant: {pending_receipt.get('merchant', 'Unknown')}\n"
                f"- Date: {pending_receipt.get('date', 'today')}\n"
                f"- Total: {pending_receipt.get('total_amount', 0)} {pending_receipt.get('currency', 'EUR')}\n"
                f"- Category: {pending_receipt.get('category', 'Food')}/{pending_receipt.get('subcategory', '')}\n"
                f"- Items: {len(pending_receipt.get('items', []))} items\n"
                f"- tg_file_id: {pending_receipt.get('tg_file_id', '')}\n\n"
                f"If the user confirms (says 'yes', 'да', 'так', 'запиши', or clicks a confirm button), "
                f"call add_transaction with the receipt data above. Do NOT ask for more information.\n"
                f"If the user wants to correct something, update the relevant field and confirm again.\n"
                f"If the user cancels, acknowledge and clear."
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

        # Build multi-turn messages: prepend recent conversation history so Claude
        # has genuine context of prior exchanges (not just text in system prompt).
        import db as _db
        try:
            history_messages = await _db.get_recent_messages_for_api(
                session.user_id, n_turns=6, telegram_bot=telegram_bot
            ) if _db.is_ready() else []
        except Exception:
            history_messages = []

        # Trim history: remove last turn if it is the same as current user message
        # (avoids duplicating the message that is about to be sent).
        if history_messages and history_messages[-1]["role"] == "user":
            history_messages.pop()

        messages = history_messages + [{"role": "user", "content": user_content}]

        # Agentic loop
        max_iterations = 5
        last_text = ""

        for iteration in range(max_iterations):
            response = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
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
                _tools_called = []   # accumulate for DB logging

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await self._execute_tool(block.name, block.input, session)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
                    # Collect for DB: skip read-only / noisy tools
                    _SKIP_LOG_TOOLS = {
                        "get_budget_status", "get_summary", "get_intelligence",
                        "find_transactions", "list_envelopes", "search_history",
                        "get_contribution_status", "get_reference_data",
                    }
                    if block.name not in _SKIP_LOG_TOOLS:
                        status = result.get("status", "") if isinstance(result, dict) else ""
                        msg = result.get("message", "") if isinstance(result, dict) else ""
                        err = result.get("error", "") if isinstance(result, dict) else ""
                        summary = (msg or err or status)[:200]
                        _tools_called.append((block.name, summary))

                # Persist tool calls to DB so next session history has them
                import db as _db_log
                if _db_log.is_ready() and _tools_called:
                    try:
                        for tool_name, tool_summary in _tools_called:
                            await _db_log.log_message(
                                user_id=session.user_id,
                                direction="bot",
                                message_type="tool",
                                raw_text=f"[tool:{tool_name}] {tool_summary}",
                                tool_called=tool_name,
                                result_short=tool_summary,
                                session_id=session.session_id,
                                envelope_id=session.current_envelope_id or "",
                            )
                    except Exception:
                        pass

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
            tool_sort_transactions, tool_find_transactions,
        )
        from tools.summary import tool_get_summary, tool_get_budget_status, tool_get_contribution_status
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
            "sort_transactions":      tool_sort_transactions,
            "find_transactions":      tool_find_transactions,
            "get_summary":              tool_get_summary,
            "get_budget_status":        tool_get_budget_status,
            "get_contribution_status":  tool_get_contribution_status,
            "import_wise_csv":        tool_import_wise_csv,
            "set_fx_rate":            tool_set_fx_rate,
            "update_config":          tool_update_config,
            "add_authorized_user":    tool_add_authorized_user,
            "remove_authorized_user": tool_remove_authorized_user,
            "create_envelope":        tool_create_envelope,
            # Intelligence tools (v2.0)
            "save_goal":              self._tool_save_goal,
            "get_intelligence":       self._tool_get_intelligence,
            # History search
            "search_history":         self._tool_search_history,
            # Dashboard writer
            "refresh_dashboard":      self._tool_refresh_dashboard,
            # Reference data
            "get_reference_data":     self._tool_get_reference_data,
            # Self-learning
            "save_learning":          self._tool_save_learning,
            # Receipt storage
            "save_receipt":           self._tool_save_receipt,
            # Learning summary → Google Sheets
            "refresh_learning_summary": self._tool_refresh_learning_summary,
            # Dashboard config management
            "update_dashboard_config":  self._tool_update_dashboard_config,
            # Inline choice buttons for user confirmation
            "present_options":          self._tool_present_options,
            # Store receipt data in session for cross-message persistence
            "store_pending_receipt":    self._tool_store_pending_receipt,
        }

        handler = dispatch.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            result = await handler(params, session, self.sheets, self.auth)
            # Write audit log for state-changing operations
            if name not in ("find_transactions", "get_summary", "get_budget_status",
                            "list_envelopes", "get_intelligence", "search_history",
                            "get_contribution_status", "refresh_dashboard",
                            "save_learning", "save_receipt", "get_reference_data",
                            "present_options", "store_pending_receipt",
                            "update_dashboard_config"):
                self.sheets.write_audit(
                    session.user_id, session.user_name,
                    name, session.current_envelope_id,
                    json.dumps(params)[:200]
                )
            # Clear pending receipt after successful transaction add
            if name == "add_transaction" and isinstance(result, dict) and "error" not in result:
                session.pending_receipt = None

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

    async def _tool_search_history(self, params: dict, session: SessionContext,
                                    sheets: SheetsClient, auth: AuthManager) -> Any:
        """Search conversation history — deeper than the 10-message rolling window."""
        import db as appdb

        if not appdb.is_ready():
            return {"error": "Conversation history unavailable (PostgreSQL not connected)"}

        keyword = params.get("keyword", "")
        limit   = min(int(params.get("limit", 20)), 50)
        offset  = int(params.get("offset", 0))

        try:
            rows = await appdb.search_conversation_history(
                session.user_id, keyword=keyword, limit=limit, offset=offset
            )
            if not rows:
                msg = (
                    f"No messages found" +
                    (f" matching '{keyword}'" if keyword else "") +
                    (f" at offset {offset}" if offset > 0 else "")
                )
                return {"status": "empty", "message": msg, "rows": []}

            formatted = appdb.format_context_for_prompt(rows)
            return {
                "status": "ok",
                "count": len(rows),
                "offset": offset,
                "has_more": len(rows) == limit,
                "messages": formatted,
            }
        except Exception as e:
            logger.error(f"search_history failed: {e}")
            return {"error": str(e)}

    async def _tool_refresh_dashboard(self, params: dict, session: SessionContext,
                                       sheets: SheetsClient, auth: AuthManager):
        """Compute current budget snapshot + contribution status and write to Dashboard tab."""
        if not auth.can_write(session.user_id):
            return {"error": "Permission denied."}

        envelope_id = params.get("envelope_id") or session.current_envelope_id
        if not envelope_id:
            return {"error": "Конверт не выбран."}

        # Find the file_id for the envelope
        envelopes = sheets.get_envelopes()
        file_id = None
        for e in envelopes:
            if e.get("ID") == envelope_id:
                file_id = e["file_id"]
                break
        if not file_id:
            return {"error": f"Конверт {envelope_id} не найден."}

        month = params.get("month") or datetime.utcnow().strftime("%Y-%m")

        from intelligence import (IntelligenceEngine, compute_contribution_status,
                                   compute_contribution_history)

        # Budget snapshot
        try:
            engine = IntelligenceEngine(sheets)
            snap = engine.compute_snapshot(envelope_id=envelope_id)
        except Exception as e:
            logger.warning(f"refresh_dashboard: snapshot failed: {e}")
            snap = {"month": month, "cap": 0, "spent": 0, "remaining": 0,
                    "pct_used": 0, "currency": "EUR"}

        # Contribution status
        try:
            contrib_snap = compute_contribution_status(sheets, envelope_id, month)
        except Exception as e:
            logger.warning(f"refresh_dashboard: contrib_snap failed: {e}")
            contrib_snap = None

        # Read dashboard config to determine history depth
        try:
            dash_cfg = sheets.get_dashboard_config()
            history_months = int(dash_cfg.get("history_months", 3))
            show_history = str(dash_cfg.get("show_contribution_history", "TRUE")).upper() == "TRUE"
        except Exception:
            history_months = 3
            show_history = True

        # Multi-month history (if enabled in config)
        contrib_history = None
        if show_history:
            try:
                contrib_history = compute_contribution_history(
                    sheets, envelope_id, months_back=history_months
                )
            except Exception as e:
                logger.warning(f"refresh_dashboard: contrib_history failed: {e}")

        try:
            sheets.update_dashboard_sheet(file_id, snap, contrib_snap, contrib_history)
        except Exception as e:
            return {"error": f"Не удалось обновить Dashboard: {e}"}

        return {
            "status": "ok",
            "message": (
                f"✓ Dashboard обновлён за {month} — "
                f"расходы {snap.get('spent', 0):,.2f} {snap.get('currency', 'EUR')} "
                f"из {snap.get('cap', 0):,.2f} ({snap.get('pct_used', 0):.1f}%)"
            ),
        }

    async def _tool_get_reference_data(self, params: dict, session: SessionContext,
                                        sheets: SheetsClient, auth: AuthManager):
        """Return reference lists (categories, who, accounts, currencies) for the current envelope."""
        from tools.transactions import _resolve_envelope
        try:
            envelope = _resolve_envelope(params, session, sheets)
        except ValueError as e:
            return {"error": str(e)}

        try:
            ref = sheets.get_reference_data(envelope["file_id"])
        except Exception as e:
            return {"error": f"Не удалось загрузить справочник: {e}"}

        return {
            "status": "ok",
            "envelope_id": envelope["ID"],
            "categories": ref.get("categories", []),
            "subcategories": ref.get("subcategories", []),
            "accounts": ref.get("accounts", []),
            "who": ref.get("who", []),
            "currencies": ref.get("currencies", []),
            "base_currency": ref.get("base_currency", "EUR"),
        }

    async def _tool_save_learning(self, params: dict, session: SessionContext,
                                   sheets: SheetsClient, auth: AuthManager):
        """Persist a learning event to the agent_learning PostgreSQL table."""
        import db as _db
        if not _db.is_ready():
            return {"status": "skipped", "reason": "DB not available"}

        event_type = params.get("event_type", "")
        if event_type not in ("vocabulary", "correction", "confirmation",
                               "pattern", "new_value", "ambiguity_resolved"):
            return {"error": f"Unknown event_type: {event_type}"}

        # For corrections: apply confidence penalty automatically
        confidence_delta = float(params.get("confidence_delta", 0.0))
        if event_type == "correction" and confidence_delta == 0.0:
            confidence_delta = -0.3
        elif event_type == "confirmation" and confidence_delta == 0.0:
            confidence_delta = 0.1

        ok = await _db.save_learning(
            user_id=session.user_id,
            event_type=event_type,
            trigger_text=params.get("trigger", ""),
            context={"original_input": params.get("original_input", "")},
            learned=params.get("learned", {}),
            confidence_delta=confidence_delta,
            envelope_id=session.current_envelope_id or "",
        )

        if ok:
            return {
                "status": "ok",
                "message": f"✓ Learning saved: {event_type}" + (
                    f" — '{params.get('trigger')}'" if params.get("trigger") else ""
                ),
            }
        return {"error": "Failed to save learning event"}

    async def _tool_save_receipt(self, params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager):
        """Save itemized receipt data to Receipts tab."""
        try:
            import bot as _bot_module
            rs = getattr(_bot_module, "receipt_store", None)
            if rs is None:
                return {"status": "skipped", "reason": "ReceiptStore not initialized"}
            receipt_id = rs.save_receipt(
                transaction_id=params.get("transaction_id", ""),
                date=params.get("date", "") or "",
                merchant=params.get("merchant", "") or "",
                total_amount=float(params.get("total_amount", 0)),
                currency=params.get("currency", "EUR"),
                items=params.get("items", []),
                ai_summary=params.get("ai_summary", "") or "",
                raw_text=params.get("raw_text", "") or "",
                tg_file_id=params.get("tg_file_id", "") or "",
            )
            return {"status": "ok", "receipt_id": receipt_id}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_refresh_learning_summary(self, params: dict, session: SessionContext,
                                              sheets: SheetsClient, auth: AuthManager):
        """Write agent_learning summary to Admin Google Sheet Learning tab."""
        try:
            import db as _db
            if not _db.is_ready():
                return {"status": "skipped", "reason": "DB not available"}

            envelope_id   = params.get("envelope_id", "") or session.current_envelope_id or ""
            min_confidence = float(params.get("min_confidence", 0.5))

            # Load all learning rows from PostgreSQL
            rows = await _db.get_all_learning(
                user_id=session.user_id,
                envelope_id=envelope_id,
                min_confidence=min_confidence,
            )
            if not rows:
                return {"status": "ok", "message": "No learning data above threshold."}

            # Format rows for Google Sheets: [event_type, trigger, learned, confidence, updated_at]
            header = ["event_type", "trigger", "learned", "confidence", "updated_at", "envelope_id"]
            sheet_rows = [header]
            for r in rows:
                sheet_rows.append([
                    r.get("event_type", ""),
                    r.get("trigger_text", ""),
                    json.dumps(r.get("learned", {}), ensure_ascii=False),
                    str(round(r.get("confidence", 0), 3)),
                    str(r.get("updated_at", ""))[:19],
                    r.get("envelope_id", ""),
                ])

            # Write to Admin sheet Learning tab
            admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
            if not admin_id:
                return {"error": "ADMIN_SHEETS_ID not set"}

            gc = sheets._gc
            wb = gc.open_by_key(admin_id)
            try:
                ws = wb.worksheet("Learning")
                ws.clear()
            except Exception:
                ws = wb.add_worksheet(title="Learning", rows=500, cols=10)

            ws.update("A1", sheet_rows)
            count = len(sheet_rows) - 1
            return {"status": "ok", "message": f"✓ {count} learning records written to Learning tab."}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_update_dashboard_config(self, params: dict, session: SessionContext,
                                             sheets: SheetsClient, auth: AuthManager):
        """Update a DashboardConfig key in the Admin sheet."""
        if not auth.can_write(session.user_id):
            return {"error": "Permission denied."}
        key = params.get("key", "").strip()
        value = params.get("value", "").strip()
        if not key:
            return {"error": "key is required"}
        valid_keys = {
            "auto_refresh_on_transaction", "show_contribution_history",
            "history_months", "budget_warning_pct", "show_category_breakdown",
            "master_template_id", "mode", "test_file_id",
        }
        if key not in valid_keys:
            return {"error": f"Unknown config key: {key}. Valid: {', '.join(sorted(valid_keys))}"}
        try:
            sheets.write_dashboard_config(key, value)
            return {"status": "ok", "message": f"✓ DashboardConfig: {key} = {value}"}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_present_options(self, params: dict, session: SessionContext,
                                     sheets: SheetsClient, auth: AuthManager):
        """Store inline choice buttons to be attached to the next bot message."""
        choices = params.get("choices", [])
        if not choices:
            return {"error": "choices list is empty"}
        # Validate structure
        for c in choices:
            if not isinstance(c, dict) or "label" not in c or "value" not in c:
                return {"error": "Each choice must have 'label' and 'value' keys"}
        session.pending_choice = choices
        return {"status": "ok", "message": f"{len(choices)} options queued as inline buttons"}

    async def _tool_store_pending_receipt(self, params: dict, session: SessionContext,
                                           sheets: SheetsClient, auth: AuthManager):
        """Store parsed receipt data in session for cross-message persistence.
        This ensures the agent remembers receipt details when user confirms in next message."""
        receipt_data = {
            "merchant": params.get("merchant", ""),
            "date": params.get("date", ""),
            "total_amount": float(params.get("total_amount", 0)),
            "currency": params.get("currency", "EUR"),
            "category": params.get("category", ""),
            "subcategory": params.get("subcategory", ""),
            "who": params.get("who", session.user_name or ""),
            "items": params.get("items", []),
            "ai_summary": params.get("ai_summary", ""),
            "raw_text": params.get("raw_text", ""),
        }
        session.pending_receipt = receipt_data
        return {"status": "ok", "message": "Receipt data stored. Will be injected on next message."}
