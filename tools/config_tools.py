"""Config and user management tools — admin only"""
import json
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext


async def tool_update_config(params: dict, session: SessionContext,
                              sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}
    sheets.write_config(params["key"], params["value"])
    auth._loaded_at = None  # force cache reload
    return {"status": "ok", "message": f"✓ Config updated: {params['key']} = {params['value']}"}


async def tool_add_authorized_user(params: dict, session: SessionContext,
                                    sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}

    config = sheets.read_config()
    role = params["role"]
    new_user = {
        "id": params["telegram_id"],
        "name": params.get("name", str(params["telegram_id"])),
        "envelopes": params.get("envelopes", []),
    }

    if role == "admin":
        key = "admin_users"
    else:
        key = "contributor_users"

    existing = json.loads(config.get(key, "[]"))
    # Remove if already exists
    existing = [u for u in existing if u["id"] != params["telegram_id"]]
    existing.append(new_user)
    sheets.write_config(key, json.dumps(existing))
    auth._loaded_at = None

    envelopes_str = ", ".join(params.get("envelopes", [])) or "all"
    return {
        "status": "ok",
        "message": (
            f"✓ {new_user['name']} ({params['telegram_id']}) added as {role}. "
            f"Envelopes: {envelopes_str}"
        ),
    }


async def tool_remove_authorized_user(params: dict, session: SessionContext,
                                       sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}

    config = sheets.read_config()
    tid = params["telegram_id"]

    for key in ("admin_users", "contributor_users"):
        users = json.loads(config.get(key, "[]"))
        updated = [u for u in users if u["id"] != tid]
        if len(updated) != len(users):
            sheets.write_config(key, json.dumps(updated))

    auth._loaded_at = None
    return {"status": "ok", "message": f"✓ User {tid} removed."}
