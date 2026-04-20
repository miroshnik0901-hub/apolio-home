"""
tests/t266_error_log_selftest.py — T-266 self-test

Forces a tool failure in ApolioAgent._execute_tool and verifies that the
exception is persisted to the staging `error_log` table with the new
`tool_*_failed` error_type prefix added in T-266.

Run: python3 tests/t266_error_log_selftest.py

Exit 0 on success, non-zero on failure.
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env (DB creds, Google creds)
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v.strip('"').strip("'")

# Force staging DB (this test writes an error entry — must be staging)
os.environ["DATABASE_URL"] = (
    "postgresql://postgres:UtkEUYbDguSsZwUGjitMxDCUJKUWwqzf"
    "@maglev.proxy.rlwy.net:17325/railway"
)
# Force TEST sheet
os.environ["APOLIO_ENV"] = "test"


async def _run():
    import db as _db
    from auth import SessionContext
    from sheets import SheetsClient
    from auth import AuthManager
    from agent import ApolioAgent

    # Initialize DB pool (reads DATABASE_URL from env)
    ok = await _db.init_db()
    if not ok:
        print("❌ FAIL: could not init staging DB pool")
        return False

    # Count errors before
    pool = await _db.get_pool()
    async with pool.acquire() as conn:
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM error_log WHERE error_type LIKE 'tool_%_failed'"
        )

    sc = SheetsClient()
    am = AuthManager(sc.admin)
    agent = ApolioAgent(sc, am)

    # Make a minimal session
    session = SessionContext(
        user_id=360466156,
        user_name="Mikhail (T-266 test)",
        role="user",
    )
    session.current_envelope_id = ""

    # Call a tool with params that will raise inside the handler.
    # present_options requires a 'question' key — pass garbage to force a branch.
    # Easier: call list_envelopes (module-level) with invalid AuthManager payload
    # by passing a None session_id — or force error via unknown handler.
    # Simplest repeatable fault: call add_transaction with missing required fields.
    result = await agent._execute_tool(
        "add_transaction",
        {"envelope_id": "NONEXISTENT_ENVELOPE_XYZ_T266"},
        session,
    )

    # Even if it doesn't raise, we need to create one that DOES. Force via a bad tool name:
    # (dispatch returns {"error": "Unknown tool"} with no raise). Trigger raise via
    # passing invalid params to aggregate_bank_statement.
    result2 = await agent._execute_tool(
        "aggregate_bank_statement",
        {"rows": "not-a-list"},  # will raise inside tool when iterated wrongly? actually tolerated
        session,
    )

    # Force a definite exception via an internal method that accesses undefined field:
    # call save_goal with wrong param types
    result3 = await agent._execute_tool(
        "save_goal",
        None,  # None instead of dict → will raise inside handler
        session,
    )

    # Count after
    async with pool.acquire() as conn:
        after = await conn.fetchval(
            "SELECT COUNT(*) FROM error_log WHERE error_type LIKE 'tool_%_failed'"
        )

    diff = after - before
    print(f"error_log tool_*_failed before: {before}  after: {after}  diff: {diff}")
    print(f"result1 (add_transaction bad envelope): {result}")
    print(f"result2 (aggregate_bank_statement bad rows): {str(result2)[:120]}")
    print(f"result3 (save_goal None params): {result3}")

    # We expect diff >= 1 — at least one of the three forced failures must have raised
    # an exception and been caught by our T-266 except block.
    if diff < 1:
        print("❌ FAIL: no new error_log rows with tool_*_failed type")
        return False

    # Verify the latest row matches
    async with pool.acquire() as conn:
        latest = await conn.fetchrow(
            "SELECT ts, error_type, context, user_id FROM error_log "
            "WHERE error_type LIKE 'tool_%_failed' ORDER BY ts DESC LIMIT 1"
        )
    print(f"Latest error_log row: ts={latest['ts']} type={latest['error_type']!r} "
          f"user={latest['user_id']} context={latest['context'][:80]!r}")

    if "tool_" not in latest["error_type"] or "_failed" not in latest["error_type"]:
        print("❌ FAIL: latest error_type doesn't match T-266 pattern")
        return False

    if latest["user_id"] != 360466156:
        print(f"❌ FAIL: user_id mismatch (expected 360466156, got {latest['user_id']})")
        return False

    print("✅ T-266 PASS: tool failure persisted to error_log")
    return True


if __name__ == "__main__":
    ok = asyncio.run(_run())
    sys.exit(0 if ok else 1)
