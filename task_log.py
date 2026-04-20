"""
task_log.py — Apolio Home Task Log manager

Sheet: Apolio Home — Task Log (ID: 1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4)
Tab:   task_log
Cols:  ID | Date | Task | Status | Apolio Comment | Branch | Resolved At | Topic | Deploy | Confirm

Deploy values (col I, set by Claude):
    N/A      — task doesn't require a deploy (diagnostic / docs / research — no code)
    READY    — code ready, waiting for Mikhail's GO
    DEPLOYED — pushed to main, Railway deployed
    FAILED   — deploy attempted but failed

⚠️ Deploy must be set EXPLICITLY on every update_task. No auto-value on status
transitions (T-267, 2026-04-20). For tasks with no code deliverable always pass
deploy='N/A'; for code tasks ready for main push pass deploy='READY'.

Confirm values (col J, set by Mikhail):
    GO       — approved to push TO MAIN (PROD)
    HOLD     — wait, don't deploy to PROD yet
    (empty)  — not yet reviewed

⚠️ DEV vs PROD rule (critical — do not misread):
    - Work on DEV/staging (branch `dev`, bot @ApolioHomeTestBot) does NOT require GO.
      Claude executes the plan on dev autonomously: write code → push dev → run
      staging tests → self-test → set Deploy=READY. Never ask Mikhail for permission
      to work on dev — just do it.
    - GO (Confirm=GO) is Mikhail's authorization for PROD deploy ONLY
      (branch `main`, bot @ApolioHomeBot). Claude must NOT push to main without GO.
    - "Waiting for GO" = "code is on dev, tested, Deploy=READY, paused before main push".
      It does NOT mean "waiting before writing code or before pushing to dev".

Reopen-after-deploy rule:
    If a task is reopened (Status → OPEN) after a deploy, Claude must:
    1. Clear Confirm (J → empty) — previous GO is no longer valid
    2. Reset Deploy (I → READY) after the fix is done
    Mikhail then sets GO again to authorize the new push.

Usage:
    from task_log import TaskLog
    tl = TaskLog()
    tl.add_task("Fix onboarding flow", topic="Interface", deploy="N/A")
    tl.update_task("T-007", status="CLOSED", comment="Fixed", deploy="DEPLOYED")
    open_tasks = tl.get_open_tasks()
"""

import os
import json
import base64
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4"
SHEET_TAB = "task_log"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column indices (1-based)
COL_ID = 1
COL_DATE = 2
COL_TASK = 3
COL_STATUS = 4
COL_COMMENT = 5
COL_BRANCH = 6
COL_RESOLVED = 7
COL_TOPIC = 8
COL_DEPLOY = 9
COL_CONFIRM = 10
TOTAL_COLS = 10

HEADER = ["ID", "Date", "Task", "Status", "Apolio Comment", "Branch", "Resolved At", "Topic", "Deploy", "Confirm"]

DEPLOY_NA = "N/A"
DEPLOY_READY = "READY"
DEPLOY_DEPLOYED = "DEPLOYED"
DEPLOY_FAILED = "FAILED"
VALID_DEPLOY = {DEPLOY_NA, DEPLOY_READY, DEPLOY_DEPLOYED, DEPLOY_FAILED}

CONFIRM_GO = "GO"
CONFIRM_HOLD = "HOLD"

STATUS_OPEN = "OPEN"
STATUS_IN_PROCESS = "IN PROCESS"
STATUS_ON_HOLD = "ON HOLD"
STATUS_DISCUSSION = "DISCUSSION"   # needs discussion between Claude and Mikhail before action
STATUS_BLOCKED = "BLOCKED"
STATUS_CLOSED = "CLOSED"

VALID_STATUSES = {STATUS_OPEN, STATUS_IN_PROCESS, STATUS_ON_HOLD, STATUS_DISCUSSION, STATUS_BLOCKED, STATUS_CLOSED}

# VALID_TOPICS is loaded dynamically from config sheet at runtime — see TaskLog._load_config_topics()
# Fallback only used if config sheet is unreadable:
_FALLBACK_TOPICS = {
    "Interface", "Features", "Data", "Infrastructure", "AI", "Docs",
}
VALID_TOPICS: set[str] = set()  # populated by TaskLog.__init__


def _get_client() -> gspread.Client:
    sa_b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "")
    if not sa_b64:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT env var not set")
    creds_dict = json.loads(base64.b64decode(sa_b64).decode())
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


CONFIG_TAB = "config"


class TaskLog:
    def __init__(self, gc: Optional[gspread.Client] = None):
        self._gc = gc or _get_client()
        self._sh = self._gc.open_by_key(SHEET_ID)
        self._ws = self._sh.worksheet(SHEET_TAB)
        self._load_config_topics()

    def _load_config_topics(self) -> None:
        """Load valid Topic values from config sheet col B (skip header 'topic')."""
        global VALID_TOPICS
        try:
            cfg_ws = self._sh.worksheet(CONFIG_TAB)
            col_b = cfg_ws.col_values(2)  # col B = topics
            topics = {v.strip() for v in col_b if v.strip() and v.strip().lower() != "topic"}
            if topics:
                VALID_TOPICS = topics
                return
        except Exception:
            pass
        VALID_TOPICS = _FALLBACK_TOPICS

    # ── Core read ──────────────────────────────────────────────────────────────

    def _all_rows(self) -> list[dict]:
        """Return all data rows as dicts (excludes header)."""
        records = self._ws.get_all_records(expected_headers=HEADER)
        return records

    def get_open_tasks(self) -> list[dict]:
        """Return rows where Status is OPEN or IN PROCESS."""
        active = {STATUS_OPEN, STATUS_IN_PROCESS, STATUS_ON_HOLD}
        return [r for r in self._all_rows() if str(r.get("Status", "")).upper() in active]

    def get_all_tasks(self) -> list[dict]:
        return self._all_rows()

    # ── Auto-numbering ─────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        """Return next sequential task ID."""
        data = self._ws.get_all_values()
        max_id = 0
        for row in data[1:]:  # skip header
            try:
                val = row[COL_ID - 1]
                # Handle both numeric and T-NNN format
                if isinstance(val, int):
                    max_id = max(max_id, val)
                elif isinstance(val, str) and val.startswith("T-"):
                    max_id = max(max_id, int(val[2:]))
                elif str(val).isdigit():
                    max_id = max(max_id, int(val))
            except (ValueError, IndexError):
                pass
        return max_id + 1

    def _fmt_id(self, n: int) -> str:
        return f"T-{n:03d}"

    # ── Write operations ───────────────────────────────────────────────────────

    def add_task(
        self,
        task: str,
        status: str = STATUS_OPEN,
        topic: str = "",
        comment: str = "",
        branch: str = "",
        deploy: str = "",
    ) -> str:
        """Add a new task row. Returns the assigned task ID string (e.g. 'T-007')."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")
        if not topic or topic not in VALID_TOPICS:
            raise ValueError(f"Topic is required and must be one of {VALID_TOPICS}. Got: '{topic}'")
        if deploy and deploy not in VALID_DEPLOY:
            raise ValueError(f"Invalid deploy '{deploy}'. Must be one of {VALID_DEPLOY}")

        task_id = self._next_id()
        today = datetime.now().strftime("%Y-%m-%d")

        row = [""] * TOTAL_COLS
        row[COL_ID - 1] = self._fmt_id(task_id)
        row[COL_DATE - 1] = today
        row[COL_TASK - 1] = task
        row[COL_STATUS - 1] = status
        row[COL_COMMENT - 1] = comment
        row[COL_BRANCH - 1] = branch
        row[COL_RESOLVED - 1] = ""
        row[COL_TOPIC - 1] = topic
        row[COL_DEPLOY - 1] = deploy
        row[COL_CONFIRM - 1] = ""

        # T-256: insert at row 2 (right under header) instead of append_row.
        # Reason: archiveClosed() Apps Script physically pushes CLOSED rows to
        # the absolute bottom of the sheet; gspread's append_row then lands
        # new tasks BELOW the CLOSED block where user cannot see them.
        # Inserting at index=2 keeps new tasks visible at the top, consistent
        # with the "Sort by Date (newest first)" Apps Script menu action.
        self._ws.insert_row(row, index=2, value_input_option="USER_ENTERED")
        return self._fmt_id(task_id)

    def update_task(
        self,
        task_id: str | int,
        status: Optional[str] = None,
        comment: Optional[str] = None,
        branch: Optional[str] = None,
        resolved_at: Optional[str] = None,
        topic: Optional[str] = None,
        deploy: Optional[str] = None,
        confirm: Optional[str] = None,
    ) -> bool:
        """Update fields on an existing task. task_id can be 'T-007' or 7.

        Reopen-after-deploy rule: when status is set back to OPEN and the task
        previously had a DEPLOYED state, pass deploy='READY' and confirm='' to
        reset the deploy cycle — the old GO is no longer valid.
        """
        if isinstance(task_id, int):
            task_id = self._fmt_id(task_id)

        data = self._ws.get_all_values()
        for i, row in enumerate(data[1:], start=2):
            row_id = str(row[COL_ID - 1]).strip()
            if row_id.upper() == task_id.upper():
                updates = {}
                if status is not None:
                    updates[COL_STATUS] = status
                    if status in {STATUS_CLOSED, STATUS_BLOCKED, STATUS_DISCUSSION} and not row[COL_RESOLVED - 1]:
                        updates[COL_RESOLVED] = resolved_at or datetime.now().strftime("%Y-%m-%d %H:%M")
                    elif status in {STATUS_OPEN, STATUS_IN_PROCESS, STATUS_ON_HOLD}:
                        updates[COL_RESOLVED] = ""
                    # T-267 (2026-04-20): Deploy is NOT auto-set on DISCUSSION.
                    # Previous auto-set (DISCUSSION + empty Deploy → READY) was wrong:
                    # diagnostic/docs/research tasks have no code to deploy and must
                    # carry Deploy=N/A. Caller must pass `deploy=` explicitly —
                    # READY for code tasks ready for PROD push, N/A for no-code tasks.
                if comment is not None:
                    updates[COL_COMMENT] = comment
                if branch is not None:
                    updates[COL_BRANCH] = branch
                if resolved_at is not None:
                    updates[COL_RESOLVED] = resolved_at
                if topic is not None:
                    if topic and topic not in VALID_TOPICS:
                        raise ValueError(f"Invalid topic '{topic}'. Must be one of {VALID_TOPICS}")
                    updates[COL_TOPIC] = topic
                if deploy is not None:
                    updates[COL_DEPLOY] = deploy
                if confirm is not None:
                    updates[COL_CONFIRM] = confirm  # pass "" to clear

                for col, val in updates.items():
                    self._ws.update_cell(i, col, val)
                return True
        return False

    def close_task(self, task_id: str | int, comment: str = "", branch: str = "") -> bool:
        """Convenience: set status to CLOSED and fill Resolved At."""
        return self.update_task(
            task_id,
            status=STATUS_CLOSED,
            comment=comment or None,
            branch=branch or None,
        )

    # ── Summary for agent ──────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a short text summary suitable for the agent context."""
        all_tasks = self._all_rows()
        by_status = {}
        for t in all_tasks:
            s = str(t.get("Status", "UNKNOWN")).upper()
            by_status[s] = by_status.get(s, 0) + 1

        lines = ["📋 Task Log summary:"]
        for s in [STATUS_OPEN, STATUS_IN_PROCESS, STATUS_ON_HOLD, STATUS_BLOCKED, STATUS_CLOSED]:
            count = by_status.get(s, 0)
            if count:
                lines.append(f"  {s}: {count}")
        if by_status.get("UNKNOWN"):
            lines.append(f"  (other): {by_status['UNKNOWN']}")

        open_tasks = [t for t in all_tasks if str(t.get("Status", "")).upper() in {STATUS_OPEN, STATUS_IN_PROCESS}]
        if open_tasks:
            lines.append("\nActive tasks:")
            for t in open_tasks[:5]:
                lines.append(f"  [{t.get('ID')}] {t.get('Task', '')[:60]} — {t.get('Topic', '')}")
            if len(open_tasks) > 5:
                lines.append(f"  … and {len(open_tasks) - 5} more")

        return "\n".join(lines)
