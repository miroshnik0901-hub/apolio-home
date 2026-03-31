import re


def md(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(chars)}])', r'\\\1', str(text))


def bar(pct: float, width: int = 10) -> str:
    """ASCII progress bar."""
    filled = round(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


def fmt_eur(amount: float) -> str:
    return f"{amount:,.2f} EUR".replace(",", " ")


def summary_envelope_a(data: dict, month: str) -> str:
    lines = [
        f"📊 *{md(month)} — MM Budget*\n",
        f"Contributed:  {md(fmt_eur(data['contributed_mikhail']))} \\(Mikhail\\)"
        + (f" \\+ {md(fmt_eur(data['contributed_marina']))} \\(Marina\\)"
           if data.get('contributed_marina') else ""),
        f"Total spent:  {md(fmt_eur(data['total_spent']))}",
        f"Balance:      {md(fmt_eur(data['balance']))} "
        + ("✓" if data['balance'] >= 0 else "⚠️"),
        "",
        "*By category:*",
    ]
    total = data['total_spent'] or 1
    for cat, amount in sorted(data['categories'].items(),
                               key=lambda x: -x[1]):
        pct = amount / total * 100
        lines.append(
            f"{md(cat):<22} {md(fmt_eur(amount))}  "
            f"{bar(pct)}  {round(pct)}%"
        )
    if data.get('prev_month_pct'):
        arrow = "↑" if data['prev_month_pct'] > 0 else "↓"
        lines.append(
            f"\nvs last month: {md(str(abs(round(data['prev_month_pct']))))}% "
            f"{arrow}  ·  Budget used: {md(str(round(data['budget_used_pct'])))}%"
        )
    return "\n".join(lines)


def summary_envelope_b(data: dict, month: str) -> str:
    cap = data.get('cap', 0)
    spent = data.get('total_spent', 0)
    remaining = cap - spent
    pct = spent / cap * 100 if cap else 0

    lines = [
        f"👧 *{md(month)} — Polina*\n",
        f"Budget: {md(fmt_eur(cap))}  ·  "
        f"Spent: {md(fmt_eur(spent))}  ·  "
        f"Remaining: {md(fmt_eur(remaining))} "
        + ("✓" if remaining >= 0 else "⚠️"),
        f"{bar(pct)} {round(pct)}%",
        "",
    ]
    total = spent or 1
    for cat, amount in sorted(data['categories'].items(),
                               key=lambda x: -x[1]):
        p = amount / total * 100
        lines.append(
            f"{md(cat):<22} {md(fmt_eur(amount))}  "
            f"{bar(p)}  {round(p)}%"
        )
    return "\n".join(lines)
