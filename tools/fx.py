"""FX rate tools + ECB auto-fetch"""
import aiohttp
from datetime import datetime
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext


ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/"
    "M.{currency}.EUR.SP00.A?lastNObservations=1&format=jsondata"
)


async def fetch_ecb_rate(currency: str) -> float | None:
    """Fetch latest monthly ECB rate for given currency vs EUR."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ECB_URL.format(currency=currency),
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                obs = data["dataSets"][0]["series"]["0:0:0:0:0"]["observations"]
                # Get the last observation value
                last_key = max(obs.keys(), key=int)
                return float(obs[last_key][0])
    except Exception:
        return None


async def tool_set_fx_rate(params: dict, session: SessionContext,
                            sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}

    month = params["month"]
    currency = params["currency"].upper()
    rate = float(params["rate"])

    ws = sheets.admin.worksheet("FX_Rates")
    rows = ws.get_all_values()
    headers = rows[0] if rows else []

    # Find or create column for currency
    if currency not in headers:
        col = len(headers) + 1
        ws.update_cell(1, col, currency)
        headers.append(currency)

    currency_col = headers.index(currency) + 1

    # Find or create row for month
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == month:
            ws.update_cell(i, currency_col, rate)
            return {"status": "ok",
                    "message": f"✓ FX rate set: {month} {currency} = {rate}"}

    # New row
    new_row = [""] * len(headers)
    new_row[0] = month
    new_row[currency_col - 1] = rate
    ws.append_row(new_row)

    return {"status": "ok",
            "message": f"✓ FX rate added: {month} {currency} = {rate}"}


async def auto_update_fx_rates(sheets: SheetsClient):
    """Called on 1st of each month to auto-fetch ECB rates."""
    month = datetime.now().strftime("%Y-%m")
    for currency in ("PLN", "UAH", "GBP", "USD"):
        rate = await fetch_ecb_rate(currency)
        if rate:
            await tool_set_fx_rate(
                {"month": month, "currency": currency, "rate": rate},
                type("S", (), {"user_id": 0, "user_name": "system",
                               "role": "admin", "current_envelope_id": ""})(),
                sheets,
                type("A", (), {"is_admin": lambda self, x: True})(),
            )
