# Week 5 Test Results

**46 / 46 checks passed**

| # | Scenario | Result | Detail |
|---|---|---|---|
| 1 | 1a Normal invoice completes automatically | PASS | All required fields present and valid |
| 2 | 1b Normal resume completes automatically | PASS | All required fields present and valid |
| 3 | 1c Second invoice (different date/total labels) completes | PASS | All required fields present and valid |
| 4 | 1d Second resume completes | PASS | All required fields present and valid |
| 5 | 1e Audit log has Uploaded -> Processing -> Auto-approved -> Completed | PASS | Uploaded / Processing started / Classified & extracted / Validated / Auto-approved by rules / Workflow completed |
| 6 | 1f Files moved into type folders | PASS |  |
| 7 | 2a Invoice missing total -> Needs Review | PASS | Missing required field(s): total_amount |
| 8 | 2b Exactly the failed field is recorded | PASS | ['total_amount'] |
| 9 | 2c Resume missing email -> Needs Review | PASS | Missing required field(s): email |
| 10 | 3a Blank/unreadable image -> Needs Review (no crash) | PASS | No readable text could be extracted (unreadable or scanned document) |
| 11 | 3b Scanned invoice image is OCR'd and routed (Completed or Needs Review, never failed) | PASS | Completed: ok |
| 12 | 4 Duplicate upload is blocked and audited | PASS | Duplicate: this file is already stored as 'invoice_normal.pdf' (ID 1). |
| 13 | 5a Invalid date -> Needs Review, 'date' recorded invalid | PASS | {'date': 'not a recognised date'} |
| 14 | 5b Zero amount -> Needs Review, 'total_amount' invalid | PASS | {'total_amount': 'not a positive number'} |
| 15 | 5c Validator flags bad email and bad phone | PASS | {'email': 'not a valid email address', 'phone': 'not a valid phone number'} |
| 16 | 5d Amount parsing handles formats | PASS |  |
| 17 | 6a Unsupported type 'Other' -> Needs Review | PASS | Document type 'Other' has no automated rules |
| 18 | 6b Rule classifier stores NO confidence (never invented) | PASS |  |
| 19 | 6c Low confidence (0.40) -> Needs Review | PASS | Low classification confidence (0.40 < 0.60) |
| 20 | 6d High confidence (0.95) and no confidence (None) -> Approved | PASS |  |
| 21 | 6e End-to-end low-confidence classification -> Needs Review, confidence stored | PASS | Low classification confidence (0.35 < 0.60) |
| 22 | 7a Database failure on upload handled with a friendly message | PASS | Cannot open database: unable to open database file |
| 23 | 7b Storage failure handled with a friendly message | PASS | The file could not be saved to storage. |
| 24 | 7c Failed storage left no orphan database row | PASS |  |
| 25 | 7d Missing document id reported as failed, not crash | PASS | Document not found. |
| 26 | 7e Unsupported extension rejected | PASS |  |
| 27 | 7f Empty file rejected | PASS |  |
| 28 | 7g Oversized file rejected | PASS |  |
| 29 | 8a Invalid transitions are blocked (Completed->Rejected, Completed->Needs Review, Needs Review->Completed, Needs Review->New) | PASS |  |
| 30 | 8b Blocked attempt is audited and status unchanged | PASS |  |
| 31 | 8c Transition table sanity | PASS |  |
| 32 | 8d Re-running workflow on a Completed document fails safely | PASS | Cannot move a document from 'Completed' to 'Processing'. |
| 33 | 9a Reject without a reason is refused | PASS |  |
| 34 | 9b Reject updates status and audit (with reviewer reason) | PASS | Total amount genuinely absent |
| 35 | 9c Approve -> Approved -> Completed with audit | PASS | Sent to review / Reviewer approved / Workflow completed |
| 36 | 10a Mixed batch: 2 processed (invoice+resume), 1 review, 2 failed (corrupt file + missing id) | PASS | processed=2 review=1 failed=2 |
| 37 | 10b One result recorded per document | PASS |  |
| 38 | 10c Corrupt file returns to 'New' with 'Processing failed' in audit and safe message | PASS | The PDF is corrupt or cannot be opened. |
| 39 | 10d Documents after the failure were still processed | PASS |  |
| 40 | 11a Search by company | PASS | ['invoice_scanned.png', 'invoice_normal.pdf'] |
| 41 | 11b Search by invoice number (also finds the scanned copy of the same invoice) | PASS | ['invoice_scanned.png', 'invoice_normal.pdf'] |
| 42 | 11c Search by filename/type | PASS |  |
| 43 | 11d Status filter | PASS |  |
| 44 | 11e Latest action + timestamp present | PASS |  |
| 45 | 11f Metrics match the stored data | PASS | {'total': 12, 'processed': 12, 'needs_review': 5, 'approved': 0, 'rejected': 1, 'completed': 6, 'failed': 0} |
| 46 | 11g Failed count in metrics reflects the corrupt document | PASS | 1 |
