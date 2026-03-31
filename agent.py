"""
Apolio Home — AI Agent
Claude claude-sonnet-4-20250514 with tool use
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import anthropic

from sheets import SheetsClient
from auth import AuthManager, SessionContext

logger = logging.getLogger(__name__)

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
        "description": "Soft-delete a transaction. confirmed must be true to execute.",
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
]

SYSTEM_PROMPT = """You are Apolio Home — a personal AI assistant for family budget management.

You communicate in the language the user writes in (Russian, Ukrainian, English, Italian — all supported, no switching commands needed).

Current date: {today}
Current user: {user_name} (role: {role})
Current envelope: {envelope_id}

BEHAVIOR RULES:
- Act immediately for add/edit. Never ask for confirmation unless deleting.
- For delete: ask for confirmation first.
- Missing date → assume today.
- Missing category → make best guess from context, state it clearly.
- Missing envelope → use current envelope unless message contains Polina/Поліна/Bergamo/liceo keywords → switch to Polina envelope.
- Missing currency → assume EUR.
- Multi-turn corrections: "виправ на вчора" / "actually yesterday" / "cambia a ieri" → edit last transaction date.
- Respond in the same language the user wrote in.
- Keep responses short and factual. Confirm what was done in one line.
- For reports: use formatted text with emoji. Send chart only when explicitly requested.

ENVELOPE SWITCHING KEYWORDS (any language):
→ Polina envelope: Polina, Поліна, Полина, дочка, daughter, Bergamo, Бергамо, liceo
→ Joint envelope: default for all other messages
"""


class ApolioAgent:
    def __init__(self, sheets: SheetsClient, auth: AuthManager):
        self.sheets = sheets
        self.auth = auth
        self.client = anthropic.Anthropic()

    async def run(self, message: str, session: SessionContext,
                  media_type: str = "text",
                  media_data: bytes | None = None) -> str:
        """
        Run the agent with a user message.
        Returns the bot's text response.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        system = SYSTEM_PROMPT.format(
            today=today,
            user_name=session.user_name,
            role=session.role,
            envelope_id=session.current_envelope_id or "not set",
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
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                # Extract final text
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return "Done."

            if response.stop_reason == "tool_use":
                # Process tool calls
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await self._execute_tool(
                        block.name, block.input, session
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                messages.append({"role": "user", "content": tool_results})

        return "Processing complete."

    async def _execute_tool(self, name: str, params: dict,
                             session: SessionContext) -> Any:
        """Dispatch tool call to the appropriate handler."""
        from tools.transactions import (
            tool_add_transaction, tool_edit_transaction,
            tool_delete_transaction, tool_find_transactions,
        )
        from tools.summary import tool_get_summary, tool_get_budget_status
        from tools.wise import tool_import_wise_csv
        from tools.fx import tool_set_fx_rate
        from tools.config_tools import (
            tool_update_config, tool_add_authorized_user,
            tool_remove_authorized_user,
        )
        from tools.envelope_tools import tool_create_envelope

        dispatch = {
            "add_transaction":       tool_add_transaction,
            "edit_transaction":      tool_edit_transaction,
            "delete_transaction":    tool_delete_transaction,
            "find_transactions":     tool_find_transactions,
            "get_summary":           tool_get_summary,
            "get_budget_status":     tool_get_budget_status,
            "import_wise_csv":       tool_import_wise_csv,
            "set_fx_rate":           tool_set_fx_rate,
            "update_config":         tool_update_config,
            "add_authorized_user":   tool_add_authorized_user,
            "remove_authorized_user": tool_remove_authorized_user,
            "create_envelope":       tool_create_envelope,
        }

        handler = dispatch.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            result = await handler(params, session, self.sheets, self.auth)
            # Write audit log for state-changing operations
            if name not in ("find_transactions", "get_summary", "get_budget_status"):
                self.sheets.write_audit(
                    session.user_id, session.user_name,
                    name, session.current_envelope_id,
                    json.dumps(params)[:200]
                )
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"error": str(e)}
