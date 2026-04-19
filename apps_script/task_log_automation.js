// Apolio Home — Task Log Automation
// Project: Apolio Task Log Automation (container-bound to Task Log sheet)
//
// HOW TO INSTALL (one-time):
//   1. Open Apolio Home — Task Log in Google Sheets
//   2. Extensions → Apps Script
//   3. Paste this entire file, replacing any existing code
//   4. Save (Ctrl+S)
//   5. Run onOpen() once manually: click Run → onOpen
//   6. Refresh the spreadsheet — you'll see the 🏠 Apolio menu
//   Note: onEdit trigger installs automatically when the script is saved.
//         No manual trigger setup needed.

const SHEET_NAME = 'task_log';
const COL = { ID: 1, DATE: 2, TASK: 3, STATUS: 4, COMMENT: 5, BRANCH: 6, RESOLVED: 7, TOPIC: 8, DEPLOY: 9, CONFIRM: 10 };

const VALID_STATUSES = ['OPEN', 'IN PROCESS', 'ON HOLD', 'DISCUSSION', 'BLOCKED', 'CLOSED'];
const VALID_TOPICS   = ['AI', 'Interface', 'Infrastructure', 'Data', 'Features', 'Docs'];
const VALID_DEPLOY   = ['READY', 'DEPLOYED', 'N/A'];

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
      idCell.setValue(nextId(sheet));  // "T-001" format — consistent with Python bot
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

  // When Status changes → manage Resolved At and Deploy
  if (col === COL.STATUS) {
    const val = String(e.value || '').toUpperCase();
    const resolvedCell = sheet.getRange(row, COL.RESOLVED);
    const deployCell   = sheet.getRange(row, COL.DEPLOY);

    if (val === 'CLOSED' || val === 'BLOCKED' || val === 'DISCUSSION') {
      if (!resolvedCell.getValue()) {
        resolvedCell.setValue(new Date());
        resolvedCell.setNumberFormat('yyyy-mm-dd hh:mm');
      }
      // T-117: auto-set Deploy=READY when moving to DISCUSSION (if empty)
      if (val === 'DISCUSSION' && !deployCell.getValue()) {
        deployCell.setValue('READY');
      }
    } else if (val === 'OPEN' || val === 'IN PROCESS' || val === 'ON HOLD') {
      resolvedCell.clearContent();
    }

    // Warn on invalid status value
    if (val && !VALID_STATUSES.includes(val)) {
      SpreadsheetApp.getActiveSpreadsheet().toast(
        `⚠️ Invalid status: "${e.value}". Valid: ${VALID_STATUSES.join(', ')}`, 'Status Warning', 5
      );
    }
  }

  // Warn on invalid Topic value
  if (col === COL.TOPIC && e.value) {
    if (!VALID_TOPICS.includes(e.value)) {
      SpreadsheetApp.getActiveSpreadsheet().toast(
        `⚠️ Invalid topic: "${e.value}". Valid: ${VALID_TOPICS.join(', ')}`, 'Topic Warning', 5
      );
    }
  }

  // Warn on invalid Deploy value
  if (col === COL.DEPLOY && e.value) {
    if (!VALID_DEPLOY.includes(e.value)) {
      SpreadsheetApp.getActiveSpreadsheet().toast(
        `⚠️ Invalid deploy: "${e.value}". Valid: ${VALID_DEPLOY.join(', ')}`, 'Deploy Warning', 5
      );
    }
  }
}

// ─── Get next sequential task ID as formatted string "T-NNN" ─────────────────
function nextId(sheet) {
  const data = sheet.getDataRange().getValues();
  let max = 0;
  for (let i = 1; i < data.length; i++) {
    const raw = data[i][COL.ID - 1];
    let n = 0;
    if (typeof raw === 'number') {
      n = raw;
    } else if (typeof raw === 'string') {
      const m = raw.match(/\d+/);
      if (m) n = parseInt(m[0], 10);
    }
    if (n > max) max = n;
  }
  const next = max + 1;
  return 'T-' + String(next).padStart(3, '0');
}

// ─── Sort task_log: by Date descending ───────────────────────────────────────
function sortTaskLog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;
  const range = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  range.sort([{ column: COL.DATE, ascending: false }]);
  ss.toast('Sorted by Date (newest first)');
}

// ─── Sort by Status priority: OPEN > IN PROCESS > ON HOLD > DISCUSSION > BLOCKED > CLOSED ──
function sortByStatus() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) return;

  const statusOrder = { 'OPEN': 1, 'IN PROCESS': 2, 'ON HOLD': 3, 'DISCUSSION': 4, 'BLOCKED': 5, 'CLOSED': 6 };
  const helperCol = sheet.getLastColumn() + 1;

  const statusVals = sheet.getRange(2, COL.STATUS, lastRow - 1, 1).getValues();
  const priorities = statusVals.map(r => [statusOrder[String(r[0]).toUpperCase()] || 99]);
  sheet.getRange(2, helperCol, lastRow - 1, 1).setValues(priorities);

  const dataRange = sheet.getRange(2, 1, lastRow - 1, helperCol);
  dataRange.sort([
    { column: helperCol, ascending: true },
    { column: COL.DATE, ascending: false }
  ]);

  sheet.getRange(2, helperCol, lastRow - 1, 1).clearContent();
  ss.toast('Sorted: OPEN → IN PROCESS → ON HOLD → DISCUSSION → BLOCKED → CLOSED');
}

// ─── Archive CLOSED: physically push all CLOSED rows to the very bottom ─────
// Active tasks → top of sheet (rows 2..N).
// CLOSED tasks → absolute bottom of sheet (rows maxRows-C+1 .. maxRows).
// Between them — empty rows (visual "bottom of page" effect, not just "below others").
function archiveClosed() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 3) return;

  // 1) Read all data rows
  const data = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  const active = [];
  const closed = [];
  for (const row of data) {
    if (String(row[COL.STATUS - 1] || '').toUpperCase() === 'CLOSED') {
      closed.push(row);
    } else {
      active.push(row);
    }
  }

  // 2) Sort each group by Date desc (newest first within its block)
  const dateIdx = COL.DATE - 1;
  const dateKey = v => v instanceof Date ? v.getTime() : String(v);
  active.sort((a, b) => (dateKey(a[dateIdx]) > dateKey(b[dateIdx]) ? -1 : 1));
  closed.sort((a, b) => (dateKey(a[dateIdx]) > dateKey(b[dateIdx]) ? -1 : 1));

  // 3) Make sure sheet has enough rows for active block + visual gap + closed block
  const desiredMax = Math.max(sheet.getMaxRows(), active.length + closed.length + 50);
  if (sheet.getMaxRows() < desiredMax) {
    sheet.insertRowsAfter(sheet.getMaxRows(), desiredMax - sheet.getMaxRows());
  }
  const maxRows = sheet.getMaxRows();

  // 4) Wipe the old data block (rows 2..lastRow)
  sheet.getRange(2, 1, lastRow - 1, lastCol).clearContent();

  // 5) Write active at top (rows 2..active.length+1)
  if (active.length > 0) {
    sheet.getRange(2, 1, active.length, lastCol).setValues(active);
  }

  // 6) Write closed at the absolute bottom (rows maxRows-closed.length+1 .. maxRows)
  if (closed.length > 0) {
    const closedStart = maxRows - closed.length + 1;
    sheet.getRange(closedStart, 1, closed.length, lastCol).setValues(closed);
  }

  ss.toast(
    `Active: ${active.length} (rows 2–${active.length + 1}). ` +
    `CLOSED: ${closed.length} (rows ${maxRows - closed.length + 1}–${maxRows}).`,
    'Archived to bottom of page', 5
  );
}

// ─── Audit: highlight tasks with missing Topic or Deploy ─────────────────────
function auditTaskLog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  let issues = 0;

  // Clear previous highlights
  sheet.getRange(2, COL.TOPIC, lastRow - 1, 1).setBackground(null);
  sheet.getRange(2, COL.DEPLOY, lastRow - 1, 1).setBackground(null);

  for (let i = 0; i < data.length; i++) {
    const row = i + 2;
    const status = String(data[i][COL.STATUS - 1] || '').toUpperCase();
    const topic  = String(data[i][COL.TOPIC - 1] || '').trim();
    const deploy = String(data[i][COL.DEPLOY - 1] || '').trim();

    if (status === 'CLOSED') continue; // skip closed for deploy check

    if (!topic) {
      sheet.getRange(row, COL.TOPIC).setBackground('#FFF3CD');
      issues++;
    }
    if (!deploy) {
      sheet.getRange(row, COL.DEPLOY).setBackground('#FFF3CD');
      issues++;
    }
    if (deploy === 'DEPLOYED' && !data[i][COL.CONFIRM - 1]) {
      sheet.getRange(row, COL.DEPLOY).setBackground('#F8D7DA');
      sheet.getRange(row, COL.CONFIRM).setBackground('#F8D7DA');
      issues++;
    }
  }

  ss.toast(issues === 0 ? '✅ No issues found' : `⚠️ ${issues} field(s) need attention (yellow=missing, red=DEPLOYED without GO)`);
}

// ─── Setup filter row ─────────────────────────────────────────────────────────
function setupFilter() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet.getFilter()) {
    sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).createFilter();
    ss.toast('Filter row added. Use Status (D) and Topic (H) dropdowns to filter.');
  } else {
    ss.toast('Filter already exists.');
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
    .addItem('Audit: check missing fields', 'auditTaskLog')
    .addItem('Setup filter row', 'setupFilter')
    .addToUi();
}
