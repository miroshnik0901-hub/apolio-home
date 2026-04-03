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
const COL = { ID: 1, DATE: 2, TASK: 3, STATUS: 4, COMMENT: 5, BRANCH: 6, RESOLVED: 7, TOPIC: 8 };

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
      idCell.setValue(nextId(sheet));
      idCell.setNumberFormat('"T-"000');
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
    if (val === 'CLOSED' || val === 'BLOCKED') {
      if (!resolvedCell.getValue()) {
        resolvedCell.setValue(new Date());
        resolvedCell.setNumberFormat('yyyy-mm-dd');
      }
    } else if (val === 'OPEN' || val === 'IN PROCESS' || val === 'ON HOLD') {
      resolvedCell.clearContent();
    }
  }
}

// ─── Get next sequential task ID (returns number, formatted as T-NNN by setNumberFormat) ─
function nextId(sheet) {
  const data = sheet.getDataRange().getValues();
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const id = data[i][COL.ID - 1];
    if (typeof id === 'number' && id > max) max = id;
  }
  return max + 1;
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
function sortByStatus() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;

  // Map statuses to priority numbers for sorting
  const statusOrder = { 'OPEN': 1, 'IN PROCESS': 2, 'ON HOLD': 3, 'BLOCKED': 4, 'CLOSED': 5 };
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();

  data.sort((a, b) => {
    const sA = statusOrder[String(a[COL.STATUS - 1]).toUpperCase()] || 99;
    const sB = statusOrder[String(b[COL.STATUS - 1]).toUpperCase()] || 99;
    if (sA !== sB) return sA - sB;
    // Secondary: Date descending
    return new Date(b[COL.DATE - 1]) - new Date(a[COL.DATE - 1]);
  });

  dataRange.setValues(data);
  SpreadsheetApp.getActiveSpreadsheet().toast('Sorted: OPEN → IN PROCESS → ON HOLD → BLOCKED → CLOSED');
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
    .createMenu('🤖 Apolio')
    .addItem('Sort by Date (newest first)', 'sortTaskLog')
    .addItem('Sort by Status priority', 'sortByStatus')
    .addSeparator()
    .addItem('Setup filter row', 'setupFilter')
    .addToUi();
}
