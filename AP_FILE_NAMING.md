# Apolio Runtime Scripts — Naming Convention

Prefix: `ap_` (lowercase). All executable utility scripts in the Apolio system use this prefix.

## Format
```
ap_{function}_{target}.{ext}
```

- `ap_` — mandatory prefix, identifies Apolio system file
- `{function}` — what it does: `read`, `scan`, `parse`, `build`, `render`, `calc`, `sync`
- `{target}` — what it works with: `drive`, `gmail`, `sheets`, `tg`, `index`, `dashboard`
- `{ext}` — matches language: `.js`, `.gs` (Apps Script), `.py`, `.ts`

## Examples
```
ap_scan_drive.js
ap_read_gmail.gs
ap_parse_tg.js
ap_build_index.py
ap_render_dashboard.js
ap_calc_freshness.js
ap_sync_sheets.gs
```

## Rules
1. snake_case only
2. No version numbers in filename — use header comment inside file
3. One responsibility per file — don't combine reader + builder
4. Keep names short — 2-3 words after `ap_`
