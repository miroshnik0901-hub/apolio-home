"""
Apolio Home — Report Formatting
Formats structured data from agent tools into Telegram-ready text.
"""
import re
from typing import Optional

CATEGORY_EMOJI = {
    "Housing":       "🏠",
    "Food":          "🍕",
    "Transport":     "🚗",
    "Health":        "💊",
    "Entertainment": "🎬",
    "Personal":      "👤",
    "Household":     "🔧",
    "Education":     "🎓",
    "Other":         "📦",
    "Income":        "💰",
    "Transfer":      "↔️",
    "Savings":       "🏦",
    "Travel":        "✈️",
    "Subscriptions": "📱",
    "Children":      "👧",
    "Жильё":         "🏠",
    "Еда":           "🍕",
    "Транспорт":     "🚗",
    "Здоровье":      "💊",
}

MONTH_NAMES_RU = {
    "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
    "05": "Май",    "06": "Июнь",    "07": "Июль", "08": "Август",
    "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь",
}


def _month_name(yyyymm: str) -> str:
    """Convert '2026-04' to 'Апрель 2026'."""
    try:
        year, month = yyyymm.split("-")
        return f"{MONTH_NAMES_RU.get(month, month)} {year}"
    except Exception:
        return yyyymm


def format_bar(pct: float, width: int = 8) -> str:
    """Render a simple ASCII progress bar."""
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def format_budget_status(data: dict) -> str:
    """
    Format the result of tool_get_budget_status as a Telegram message.
    data keys: envelope_id, month, cap, spent, remaining, pct_used, alert
    """
    month_label = _month_name(data.get("month", ""))
    env_id = data.get("envelope_id", "")
    cap = data.get("cap", 0)
    spent = data.get("spent", 0)
    remaining = data.get("remaining", 0)
    pct = data.get("pct_used", 0)
    alert = data.get("alert", False)

    alert_emoji = "🔴" if pct >= 90 else ("🟡" if alert else "🟢")

    lines = [
        f"📊 *{month_label} — {env_id}*",
        "",
        f"{alert_emoji} Потрачено: *{spent:,.2f}* из *{cap:,.0f} EUR* ({pct:.0f}%)",
        f"Осталось: *{remaining:,.2f} EUR*",
    ]
    return "\n".join(lines)


def format_report(data: dict, envelope_id: str = "", cap: float = 0) -> str:
    """
    Format the result of tool_get_summary as a Telegram message with category bars.
    data keys: envelope_id, period, total_spent, categories, by_who
    """
    period = data.get("period", "")
    month_label = _month_name(period) if "-" in period else period
    env = envelope_id or data.get("envelope_id", "")
    total = float(data.get("total_spent", 0))
    categories = data.get("categories", {})

    lines = [f"📋 *{month_label} — {env}*", ""]

    if cap and cap > 0:
        pct_total = round(total / cap * 100, 1)
        lines.append(f"Всего: *{total:,.2f}* из *{cap:,.0f} EUR* ({pct_total:.0f}%)")
        lines.append("")

    # Sort categories by amount descending
    sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    for cat, amt in sorted_cats:
        if amt <= 0:
            continue
        pct = round(amt / total * 100) if total > 0 else 0
        emoji = CATEGORY_EMOJI.get(cat, "▸")
        lines.append(f"{emoji} {cat}: {amt:,.0f} EUR ({pct}%)")

    if not sorted_cats or total == 0:
        lines.append("Расходов за период нет.")

    # By who section (if multiple people)
    by_who = data.get("by_who", {})
    if len(by_who) > 1:
        lines.append("")
        lines.append("*По кому:*")
        for who, amt in sorted(by_who.items(), key=lambda x: x[1], reverse=True):
            pct = round(amt / total * 100) if total > 0 else 0
            lines.append(f"  {who}: {amt:,.2f} EUR ({pct}%)")

    return "\n".join(lines)


def format_transactions_list(records: list, limit: int = 10) -> str:
    """Format a list of transaction records for display."""
    if not records:
        return "Записей нет."

    lines = [f"📝 *Последние {min(len(records), limit)} записей:*\n"]
    for r in records[-limit:]:
        date = r.get("Date", "")
        amount = r.get("Amount_Orig", r.get("Amount_EUR", ""))
        currency = r.get("Currency_Orig", "EUR")
        cat = r.get("Category", "")
        note = r.get("Note", "")
        who = r.get("Who", "")
        emoji = CATEGORY_EMOJI.get(cat, "▸")

        note_part = f" · _{note}_" if note else ""
        who_part = f" · {who}" if who and who != "Mikhail" else ""
        lines.append(f"{emoji} {date}  *{amount} {currency}*  {cat}{who_part}{note_part}")

    return "\n".join(lines)


def to_html(text: str) -> str:
    """
    Convert simple Markdown-style text to HTML for Telegram parse_mode=HTML.
    Handles *bold*, _italic_, `code`, and escapes &, <, >.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r'\*(.+?)\*', r'<b>\1</b>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text
