// Apolio Home — Task Log Automation
// Project: Apolio Task Log Automation (container-bound to Task Log sheet)
//
// HOW TO INSTALL (one-time):
//   1. Open Apolio Home — Task Log in Google Sheets
//   2. Extensions → Apps Script
//   3. Paste this entire file, replacing any existing code
//   4. Save (Ctrl+S), then run onOpen() once to install the custom menu
//   5. The onEdit trigger activates automatically (no extra setup needed)

const SHEET_NAME = 'task_log';
const COL = { ID: 1, DATE: 2, TASK: 3, STATUS: 4, COMMENT: 5, BRANCH: 6, RESOLVED: 7, TOPIC: 8, DEPLOY: 9, CONFIRM: 10 };

// ─── onEdit trigger: fires when a user manually edits the sheet ───────────────
// Note: does NOT fire when the Python bot writes via Sheets API
function onEdit(e) {
  const sheet = e.source.getActiveSheet();
  if (sheet.getName() !== SHEET_NAME) return;

  const row = e.range.getRow();
  const col = e.range.getColumn();
  if (row < 2) return; // skip header row

  // When Task column (C) is filled → auto-assign ID, Date, Status
  if (col === COL.TASK && e.value) {
    const idCell = sheet.getRange(row, COL.ID);
    if (!idCell.getValue()) {
      idCell.setValue(nextId(sheet));  // plain text "T-001" — consistent with Python bot
    }
    const dateCell = sheet.getRange(row, COL.DATE);
    if (!dateCell.getValue()) {
      dateCell.setValue(new Date());
      dateCell.setNumberFormat('yyyy-mm-dd');
    }
    const statusCell = sheet.getRange(row, COL.STATUS);
    if (!statusCell.getValue()) {
      statusCell.setValue('OPEN');
    }
  }

  // When Status changes → manage Resolved At
  if (col === COL.STATUS) {
    const val = String(e.value || '').toUpperCase();
    const resolvedCell = sheet.getRange(row, COL.RESOLVED);
    if (val === 'CLOSED' || val === 'BLOCKED' || val === 'DISCUSSION') {
      if (!resolvedCell.getValue()) {
        resolvedCell.setValue(new Date());
        resolvedCell.setNumberFormat('yyyy-mm-dd hh:mm');
      }
      // T-117/T-129: auto-set Deploy=READY when moving to DISCUSSION (if empty)
      if (val === 'DISCUSSION') {
        const deployCell = sheet.getRange(row, COL.DEPLOY);
        if (!deployCell.getValue()) {
          deployCell.setValue('READY');
        }
      }
    } else if (val === 'OPEN' || val === 'IN PROCESS' || val === 'ON HOLD') {
      resolvedCell.clearContent();
    }
  }
}

// ─── Get next sequential task ID as formatted string "T-NNN" ─────────────────
// Works whether IDs were written by the Python bot ("T-001") or a previous
// onEdit run (also "T-001").  Never stores IDs as bare numbers.
function nextId(sheet) {
  const data = sheet.getDataRange().getValues();
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const raw = data[i][COL.ID - 1];
    let n = 0;
    if (typeof raw === 'number') {
      n = raw;                                    // legacy bare number
    } else if (typeof raw === 'string') {
      const m = raw.match(/\d+/);
      if (m) n = parseInt(m[0], 10);             // "T-001" → 1
    }
    if (n > max) max = n;
  }
  const next = max + 1;
  return 'T-' + String(next).padStart(3, '0');   // returns "T-002", "T-042", etc.
}

// ─── Sort task_log: active tasks first, then by Date desc ─────────────────────
function sortTaskLog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;
  const range = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  // Sort by Status (alphabetical puts BLOCKED/CLOSED at top, OPEN further down — reverse)
  // then by Date descending
  range.sort([
    { column: COL.DATE, ascending: false }
  ]);
  SpreadsheetApp.getActiveSpreadsheet().toast('Sorted by Date (newest first)');
}

// ─── Sort by Status priority: OPEN > IN PROCESS > ON HOLD > BLOCKED > CLOSED ──
// Uses a hidden helper column (last column + 1) to write a numeric priority,
// sorts by that column via native Sheets sort (safe for dates/numbers),
// then clears the helper column.
function sortByStatus() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;

  const statusOrder = { 'OPEN': 1, 'IN PROCESS': 2, 'ON HOLD': 3, 'DISCUSSION': 4, 'BLOCKED': 5, 'CLOSED': 6 };
  const helperCol = sheet.getLastColumn() + 1;

  // Write priority numbers into helper column
  const statusVals = sheet.getRange(2, COL.STATUS, lastRow - 1, 1).getValues();
  const priorities = statusVals.map(r => [statusOrder[String(r[0]).toUpperCase()] || 99]);
  sheet.getRange(2, helperCol, lastRow - 1, 1).setValues(priorities);

  // Sort by helper col asc, then by Date desc
  const dataRange = sheet.getRange(2, 1, lastRow - 1, helperCol);
  dataRange.sort([
    { column: helperCol, ascending: true },
    { column: COL.DATE, ascending: false }
  ]);

  // Clear helper column
  sheet.getRange(2, helperCol, lastRow - 1, 1).clearContent();

  SpreadsheetApp.getActiveSpreadsheet().toast('Sorted: OPEN → IN PROCESS → ON HOLD → DISCUSSION → BLOCKED → CLOSED');
}

// ─── Archive CLOSED: push all CLOSED rows to the bottom ──────────────────────
// Active tasks stay at top, CLOSED rows sink to bottom sorted by Date desc.
// Uses helper column approach (safe for dates/numbers).
function archiveClosed() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;

  const helperCol = sheet.getLastColumn() + 1;
  const statusVals = sheet.getRange(2, COL.STATUS, lastRow - 1, 1).getValues();
  // 0 = active (stays on top), 1 = CLOSED (sinks to bottom)
  const flags = statusVals.map(r => [String(r[0]).toUpperCase() === 'CLOSED' ? 1 : 0]);
  sheet.getRange(2, helperCol, lastRow - 1, 1).setValues(flags);

  const dataRange = sheet.getRange(2, 1, lastRow - 1, helperCol);
  dataRange.sort([
    { column: helperCol, ascending: true },
    { column: COL.DATE, ascending: false }
  ]);

  sheet.getRange(2, helperCol, lastRow - 1, 1).clearContent();
  SpreadsheetApp.getActiveSpreadsheet().toast('CLOSED tasks moved to bottom');
}

// ─── Setup filter row (run once) ─────────────────────────────────────────────
function setupFilter() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet.getFilter()) {
    sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).createFilter();
    SpreadsheetApp.getActiveSpreadsheet().toast('Filter row added. Use Status (D) and Topic (H) dropdowns to filter.');
  } else {
    SpreadsheetApp.getActiveSpreadsheet().toast('Filter already exists.');
  }
}

// ─── Custom menu ──────────────────────────────────────────────────────────────
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🏠 Apolio')
    .addItem('Sort by Date (newest first)', 'sortTaskLog')
    .addItem('Sort by Status priority', 'sortByStatus')
    .addItem('Archive CLOSED → move to bottom', 'archiveClosed')
    .addSeparator()
    .addItem('Setup filter row', 'setupFilter')
    .addToUi();
}
