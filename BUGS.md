# BUGS Log

Use this file to track runtime bugs, repro steps, and fix status.

## Entry Template

- Date:
- Title:
- Severity: `low | medium | high | critical`
- Environment: `local / staging / prod`
- File/Area:
- Repro Steps:
  1.
  2.
  3.
- Expected Result:
- Actual Result:
- Error/Trace:
- Root Cause (if known):
- Fix Plan:
- Status: `open | in_progress | blocked | resolved`
- Owner:
- PR/Commit:

---

## Bugs

### 2026-02-28 - Barcode runtime dependency missing
- Severity: high
- Environment: local
- File/Area: `app/services/barcode_service.py`
- Repro Steps:
  1. Start backend.
  2. Upload barcode image to `/image/barcode`.
  3. Observe runtime message about pyzbar/zbar.
- Expected Result: UPC/EAN barcode decodes.
- Actual Result: `zbar` runtime missing on Windows in some setups.
- Error/Trace: `pyzbar/zbar not available in runtime`
- Root Cause (if known): Native `zbar` DLL not installed or not discoverable.
- Fix Plan: Use OpenCV QR fallback and install native zbar for full barcode support.
- Status: in_progress
- Owner: 
- PR/Commit: 
