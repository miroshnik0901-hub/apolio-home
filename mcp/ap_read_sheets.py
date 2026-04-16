#!/usr/bin/env python3
"""
Google Sheets MCP Server for Apolio CXO.

Provides read/write access to Google Sheets via the Apolio service account
(apolio-home-bot@apolio-home.iam.gserviceaccount.com).

Auth: GOOGLE_SERVICE_ACCOUNT env var — base64-encoded service account JSON.
The sheet must be shared with the service account email (editor rights).

Transport:
  - stdio (default): for local Cowork/Claude desktop MCP config
  - streamable HTTP: for Railway deployment (set PORT env var)

Usage (stdio, add to Claude desktop MCP config):
  {
    "mcpServers": {
      "apolio_sheets": {
        "command": "python3",
        "args": ["/path/to/mcp/sheets_mcp.py"],
        "env": { "GOOGLE_SERVICE_ACCOUNT": "<base64_key>" }
      }
    }
  }
"""

import base64
import json
import os
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Known Apolio sheet IDs — convenience shortcuts accepted in place of raw IDs
KNOWN_SHEETS: Dict[str, str] = {
    "prod_admin":  "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk",
    "prod_budget": "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ",
    "test_admin":  "1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM",
    "test_budget": "196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788",
    "task_log":    "1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4",
}

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _get_client() -> gspread.Client:
    """Build an authorised gspread client from GOOGLE_SERVICE_ACCOUNT env var."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT env var is not set. "
            "Set it to the base64-encoded service account JSON."
        )
    try:
        key_json = json.loads(base64.b64decode(raw).decode())
    except Exception as exc:
        raise RuntimeError(f"Failed to decode GOOGLE_SERVICE_ACCOUNT: {exc}") from exc

    creds = Credentials.from_service_account_info(key_json, scopes=SCOPES)
    return gspread.authorize(creds)


def _resolve_sheet_id(sheet_id: str) -> str:
    """Accept either a raw Sheet ID or a known alias like 'prod_budget'."""
    return KNOWN_SHEETS.get(sheet_id, sheet_id)


def _open_sheet(sheet_id: str) -> gspread.Spreadsheet:
    return _get_client().open_by_key(_resolve_sheet_id(sheet_id))


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("apolio_sheets_mcp")


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ReadRangeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sheet_id: str = Field(
        ...,
        description=(
            "Google Sheet ID (44-char string from URL) or Apolio alias: "
            "'prod_admin', 'prod_budget', 'test_admin', 'test_budget', 'task_log'"
        ),
    )
    tab: str = Field(
        ...,
        description="Worksheet (tab) name, e.g. 'Transactions', 'Summary', 'FX_Rates'",
    )
    range: Optional[str] = Field(
        default=None,
        description=(
            "A1-notation range, e.g. 'A1:F50'. "
            "Omit to return all values in the tab."
        ),
    )
    value_render: Optional[str] = Field(
        default="FORMATTED_VALUE",
        description=(
            "How cell values are rendered: "
            "'FORMATTED_VALUE' (strings, default), "
            "'UNFORMATTED_VALUE' (raw numbers/booleans), "
            "'FORMULA' (raw formula strings)"
        ),
    )


class ListTabsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sheet_id: str = Field(
        ...,
        description="Google Sheet ID or Apolio alias (see sheets_read_range for list)",
    )


class AppendRowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sheet_id: str = Field(..., description="Google Sheet ID or Apolio alias")
    tab: str = Field(..., description="Worksheet (tab) name")
    values: List[Any] = Field(
        ...,
        description="Row values as a list, e.g. ['2026-04-16', 'Coffee', 12.5, 'EUR']",
        min_length=1,
    )
    value_input_option: Optional[str] = Field(
        default="USER_ENTERED",
        description=(
            "'USER_ENTERED' (default — Sheets parses dates/formulas), "
            "'RAW' (stored as-is)"
        ),
    )


class UpdateCellInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sheet_id: str = Field(..., description="Google Sheet ID or Apolio alias")
    tab: str = Field(..., description="Worksheet (tab) name")
    cell: str = Field(
        ...,
        description="A1-notation cell address, e.g. 'B5', 'D12'",
        pattern=r"^[A-Za-z]+[0-9]+$",
    )
    value: Any = Field(..., description="New cell value (string, number, or formula)")
    value_input_option: Optional[str] = Field(
        default="USER_ENTERED",
        description="'USER_ENTERED' (default) or 'RAW'",
    )


class UpdateRangeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sheet_id: str = Field(..., description="Google Sheet ID or Apolio alias")
    tab: str = Field(..., description="Worksheet (tab) name")
    range: str = Field(..., description="A1-notation range, e.g. 'A2:D10'")
    values: List[List[Any]] = Field(
        ...,
        description="2D list of values matching the range dimensions",
        min_length=1,
    )
    value_input_option: Optional[str] = Field(
        default="USER_ENTERED",
        description="'USER_ENTERED' (default) or 'RAW'",
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="sheets_list_tabs",
    annotations={
        "title": "List Worksheet Tabs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sheets_list_tabs(params: ListTabsInput) -> str:
    """List all worksheet tabs in a Google Sheets file.

    Returns tab names, row/column counts, and sheet IDs.
    Use this before reading data to confirm the exact tab name.

    Args:
        params (ListTabsInput):
            - sheet_id (str): Sheet ID or alias ('prod_budget', 'task_log', etc.)

    Returns:
        str: JSON with list of tabs:
            {
                "spreadsheet_title": str,
                "tabs": [{"title": str, "sheet_id": int, "rows": int, "cols": int}]
            }

    Examples:
        - "What tabs exist in the prod budget?" → sheet_id='prod_budget'
        - "List tabs in sheet 1erX...RhpQ"    → sheet_id='1erX...RhpQ'
    """
    try:
        ss = _open_sheet(params.sheet_id)
        tabs = [
            {
                "title": ws.title,
                "sheet_id": ws.id,
                "rows": ws.row_count,
                "cols": ws.col_count,
            }
            for ws in ss.worksheets()
        ]
        return json.dumps(
            {"spreadsheet_title": ss.title, "tabs": tabs}, ensure_ascii=False, indent=2
        )
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="sheets_read_range",
    annotations={
        "title": "Read Sheet Range",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sheets_read_range(params: ReadRangeInput) -> str:
    """Read cell values from a Google Sheets tab.

    Returns a 2D array of rows. Empty trailing rows/columns are omitted.
    First row is typically the header.

    Args:
        params (ReadRangeInput):
            - sheet_id (str): Sheet ID or alias
            - tab (str): Tab name (exact, case-sensitive)
            - range (Optional[str]): A1-notation range; omit for entire tab
            - value_render (Optional[str]): 'FORMATTED_VALUE' | 'UNFORMATTED_VALUE' | 'FORMULA'

    Returns:
        str: JSON with:
            {
                "tab": str,
                "range": str,
                "rows": int,
                "cols": int,
                "values": [[...], [...], ...]
            }

    Examples:
        - Read all transactions: tab='Transactions', range omitted
        - Read header only:      range='A1:Z1'
        - Read last 10 rows:     range='A91:Z100'
        - Read raw dates:        value_render='UNFORMATTED_VALUE'
    """
    try:
        ss = _open_sheet(params.sheet_id)
        ws = ss.worksheet(params.tab)

        render = params.value_render or "FORMATTED_VALUE"

        if params.range:
            values = ws.get(params.range, value_render_option=render)
            used_range = params.range
        else:
            values = ws.get_all_values(value_render_option=render)
            used_range = "all"

        rows = len(values)
        cols = max((len(r) for r in values), default=0)

        return json.dumps(
            {
                "tab": params.tab,
                "range": used_range,
                "rows": rows,
                "cols": cols,
                "values": values,
            },
            ensure_ascii=False,
            indent=2,
        )
    except gspread.exceptions.WorksheetNotFound:
        return f"Error: Tab '{params.tab}' not found. Use sheets_list_tabs to see available tabs."
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="sheets_append_row",
    annotations={
        "title": "Append Row to Sheet",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sheets_append_row(params: AppendRowInput) -> str:
    """Append a new row at the end of a Google Sheets tab.

    Adds one row after the last non-empty row. Does NOT overwrite existing data.
    Dates should be strings in 'YYYY-MM-DD' format; Sheets will parse them
    when value_input_option='USER_ENTERED' (default).

    Args:
        params (AppendRowInput):
            - sheet_id (str): Sheet ID or alias
            - tab (str): Tab name
            - values (List[Any]): Row values in column order
            - value_input_option (str): 'USER_ENTERED' (default) or 'RAW'

    Returns:
        str: Confirmation with updated range, e.g. "Appended row at A45:D45"

    Examples:
        - Add transaction: values=['2026-04-16', 'Coffee', 12.5, 'EUR', 'Food']
    """
    try:
        ss = _open_sheet(params.sheet_id)
        ws = ss.worksheet(params.tab)
        result = ws.append_row(
            params.values,
            value_input_option=params.value_input_option or "USER_ENTERED",
        )
        updated = result.get("updates", {}).get("updatedRange", "unknown range")
        return f"Appended row at {updated}"
    except gspread.exceptions.WorksheetNotFound:
        return f"Error: Tab '{params.tab}' not found."
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="sheets_update_cell",
    annotations={
        "title": "Update Single Cell",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sheets_update_cell(params: UpdateCellInput) -> str:
    """Update a single cell in a Google Sheets tab.

    Overwrites the cell value. Use for targeted edits (e.g., marking a row
    as deleted, correcting a category, updating a config value).

    Args:
        params (UpdateCellInput):
            - sheet_id (str): Sheet ID or alias
            - tab (str): Tab name
            - cell (str): A1-notation address, e.g. 'B12'
            - value (Any): New value
            - value_input_option (str): 'USER_ENTERED' (default) or 'RAW'

    Returns:
        str: Confirmation, e.g. "Updated B12 in 'Transactions' → 'TRUE'"

    Examples:
        - Mark row deleted: tab='Transactions', cell='H45', value='TRUE'
        - Fix category:     tab='Transactions', cell='C12', value='Food'
    """
    try:
        ss = _open_sheet(params.sheet_id)
        ws = ss.worksheet(params.tab)
        ws.update(
            [[params.value]],
            params.cell,
            value_input_option=params.value_input_option or "USER_ENTERED",
        )
        return f"Updated {params.cell} in '{params.tab}' → '{params.value}'"
    except gspread.exceptions.WorksheetNotFound:
        return f"Error: Tab '{params.tab}' not found."
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="sheets_update_range",
    annotations={
        "title": "Update Cell Range",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sheets_update_range(params: UpdateRangeInput) -> str:
    """Update a rectangular range of cells in a Google Sheets tab.

    Overwrites all cells in the range with the provided 2D values array.
    Dimensions of `values` must match the range dimensions.

    Args:
        params (UpdateRangeInput):
            - sheet_id (str): Sheet ID or alias
            - tab (str): Tab name
            - range (str): A1-notation range, e.g. 'A2:D5'
            - values (List[List[Any]]): 2D array matching range dimensions
            - value_input_option (str): 'USER_ENTERED' (default) or 'RAW'

    Returns:
        str: Confirmation with number of updated cells

    Examples:
        - Rebuild header:  range='A1:E1', values=[['Date','Note','Amount','Currency','Category']]
        - Patch 3 rows:    range='C5:C7', values=[['Food'],['Transport'],['Food']]
    """
    try:
        ss = _open_sheet(params.sheet_id)
        ws = ss.worksheet(params.tab)
        result = ws.update(
            params.values,
            params.range,
            value_input_option=params.value_input_option or "USER_ENTERED",
        )
        updated_cells = result.get("updatedCells", "?")
        return f"Updated {updated_cells} cells in '{params.tab}' range {params.range}"
    except gspread.exceptions.WorksheetNotFound:
        return f"Error: Tab '{params.tab}' not found."
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Entry point — supports both stdio and HTTP transport
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = os.environ.get("PORT")
    if port:
        # Railway / remote deployment
        mcp.run(transport="streamable_http", port=int(port))
    else:
        # Local Cowork / Claude desktop (stdio)
        mcp.run()
