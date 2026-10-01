# Week 4 - Test Results
Run date: 2026-10-01  
Documents tested: 12 valid + duplicate + 5 bad/edge-case files

**Result: 78 / 78 checks passed**

## Documents processed
| # | File | Type | Confidence | Status | Note |
|---|---|---|---|---|---|
| 1 | invoice_001.pdf | Invoice | 92% | Processed |  |
| 2 | invoice_002.pdf | Invoice | 92% | Processed |  |
| 3 | invoice_003.pdf | Invoice | 88% | Processed |  |
| 4 | invoice_004.pdf | Invoice | 71% | Processed |  |
| 5 | invoice_missing_fields.pdf | Invoice | 49% | Needs Review | Missing: Invoice Number, Total Amount |
| 6 | resume_001.pdf | Resume | 81% | Processed |  |
| 7 | resume_002.pdf | Resume | 77% | Processed |  |
| 8 | resume_missing_email.pdf | Resume | 81% | Needs Review | Missing: Email |
| 9 | other_meeting_minutes.pdf | Other | 73% | Processed |  |
| 10 | other_recipe.pdf | Other | 80% | Processed |  |
| 11 | scanned_invoice.png | Invoice | 93% | Processed |  |
| 12 | scanned_resume.png | Resume | 79% | Processed |  |

## All checks
| Result | Check | Expected | Actual |
|---|---|---|---|
| PASS | Upload invoice_001.pdf: outcome | saved | saved |
| PASS | Upload invoice_001.pdf: document type | Invoice | Invoice |
| PASS | Upload invoice_001.pdf: status | Processed | Processed |
| PASS | Upload invoice_002.pdf: outcome | saved | saved |
| PASS | Upload invoice_002.pdf: document type | Invoice | Invoice |
| PASS | Upload invoice_002.pdf: status | Processed | Processed |
| PASS | Upload invoice_003.pdf: outcome | saved | saved |
| PASS | Upload invoice_003.pdf: document type | Invoice | Invoice |
| PASS | Upload invoice_003.pdf: status | Processed | Processed |
| PASS | Upload invoice_004.pdf: outcome | saved | saved |
| PASS | Upload invoice_004.pdf: document type | Invoice | Invoice |
| PASS | Upload invoice_004.pdf: status | Processed | Processed |
| PASS | Upload invoice_missing_fields.pdf: outcome | saved | saved |
| PASS | Upload invoice_missing_fields.pdf: document type | Invoice | Invoice |
| PASS | Upload invoice_missing_fields.pdf: status | Needs Review | Needs Review |
| PASS | Upload resume_001.pdf: outcome | saved | saved |
| PASS | Upload resume_001.pdf: document type | Resume | Resume |
| PASS | Upload resume_001.pdf: status | Processed | Processed |
| PASS | Upload resume_002.pdf: outcome | saved | saved |
| PASS | Upload resume_002.pdf: document type | Resume | Resume |
| PASS | Upload resume_002.pdf: status | Processed | Processed |
| PASS | Upload resume_missing_email.pdf: outcome | saved | saved |
| PASS | Upload resume_missing_email.pdf: document type | Resume | Resume |
| PASS | Upload resume_missing_email.pdf: status | Needs Review | Needs Review |
| PASS | Upload other_meeting_minutes.pdf: outcome | saved | saved |
| PASS | Upload other_meeting_minutes.pdf: document type | Other | Other |
| PASS | Upload other_meeting_minutes.pdf: status | Processed | Processed |
| PASS | Upload other_recipe.pdf: outcome | saved | saved |
| PASS | Upload other_recipe.pdf: document type | Other | Other |
| PASS | Upload other_recipe.pdf: status | Processed | Processed |
| PASS | Upload scanned_invoice.png: outcome | saved | saved |
| PASS | Upload scanned_invoice.png: document type | Invoice | Invoice |
| PASS | Upload scanned_invoice.png: status | Processed | Processed |
| PASS | Upload scanned_resume.png: outcome | saved | saved |
| PASS | Upload scanned_resume.png: document type | Resume | Resume |
| PASS | Upload scanned_resume.png: status | Processed | Processed |
| PASS | Duplicate (same content, new name): outcome | duplicate | duplicate |
| PASS | Duplicate points to the ORIGINAL record | 1 | 1 |
| PASS | Duplicate did not create a new record | 12 | 12 |
| PASS | Unsupported type (.txt) is rejected | rejected | rejected |
| PASS | Fake image (text renamed .png) is rejected | rejected | rejected |
| PASS | Empty file is rejected | rejected | rejected |
| PASS | Oversized file (>10 MB) is rejected | rejected | rejected |
| PASS | Corrupt PDF does not crash (saved as Failed) | saved | saved |
| PASS | Corrupt PDF status | Failed | Failed |
| PASS | Corrupt PDF message is friendly (no raw exception) | True | True |
| PASS | Corrupt PDF was tracked as a record | 13 | 13 |
| PASS | OCR unavailable: no crash, status Failed | Failed | Failed |
| PASS | OCR unavailable: friendly message | True | True |
| PASS | Every file exists in the correct folder for its type | True | True |
| PASS | Stored filenames are generated (not the original names) | True | True |
| PASS | Original filenames are kept in the database | True | True |
| PASS | invoices/ folder holds only Invoice files | True | True |
| PASS | Search by company 'Delta' | ['invoice_missing_fields.pdf'] | ['invoice_missing_fields.pdf'] |
| PASS | Search by invoice number 'INV-3310' | ['invoice_003.pdf'] | ['invoice_003.pdf'] |
| PASS | Search by file name 'scanned' | ['scanned_invoice.png', 'scanned_resume.png'] | ['scanned_invoice.png', 'scanned_resume.png'] |
| PASS | Search by text preview 'vegetable' | ['other_recipe.pdf'] | ['other_recipe.pdf'] |
| PASS | Search by document type word 'Resume' finds all resumes | True | True |
| PASS | Search with no match returns nothing | [] | [] |
| PASS | Search '%' is treated as text, not a wildcard | [] | [] |
| PASS | Filter type=Invoice count | 6 | 6 |
| PASS | Filter type=Resume count | 4 | 4 |
| PASS | Filter status='Needs Review' count | 2 | 2 |
| PASS | Filter status=Failed count | 1 | 1 |
| PASS | Combined filter: Invoice + Needs Review | ['invoice_missing_fields.pdf'] | ['invoice_missing_fields.pdf'] |
| PASS | Date filter (today) includes all | 13 | 13 |
| PASS | Date filter (yesterday only) includes none | 0 | 0 |
| PASS | Sort oldest-first is the reverse of newest-first | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13] | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13] |
| PASS | Newest first puts the last upload on top | 13 | 13 |
| PASS | Update status to Processed | True | True |
| PASS | Status change was saved | Processed | Processed |
| PASS | Unknown columns cannot be updated | False | False |
| PASS | Delete removes the record | None | None |
| PASS | Delete removes the file | False | False |
| PASS | After restart (new process) saved records remain | 12 | 12 |
| PASS | Broken database: clear error outcome (no crash) | error | error |
| PASS | Broken database: message hides technical details | True | True |
| PASS | Broken database: no orphan file left behind | 12 | 12 |
