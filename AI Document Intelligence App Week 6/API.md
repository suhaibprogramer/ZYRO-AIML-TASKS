# REST API

Start: `uvicorn api:app --host 0.0.0.0 --port 8000`. Interactive documentation (generated from the code): `http://localhost:8000/docs`.

**Authentication.** If the `API_KEY` setting is not empty, every endpoint except `/health` needs the header `X-API-Key: <your key>`. Wrong or missing key → `401`.

## Endpoints

| Method | Path | Body / query | Success | Errors |
|---|---|---|---|---|
| GET | `/health` | – | `200 {"status":"ok","documents":N}` | `503` database unavailable |
| POST | `/documents` | multipart `file`; `?process=false` to only store | `201` document + workflow result | `409` duplicate (includes `existing_document_id`), `413` too large, `415` unsupported type, `422` corrupt / fake content / too many pages, `503` OCR or database unavailable |
| GET | `/documents` | `?status=`, `?type=`, `?q=`, `?limit=` | `200` list | `422` bad status |
| GET | `/documents/{id}` | – | `200` fields, validation, anomalies, timings, history, text preview | `404` |
| POST | `/documents/{id}/process` | – | `200` outcome: `processed`, `review`, `failed` or `skipped` | `404` |
| POST | `/documents/{id}/approve` | `{"note": "..."}` (optional) | `200` document | `404`, `409` not allowed in this state |
| POST | `/documents/{id}/reject` | `{"reason": "..."}` (required) | `200` document | `404`, `409`, `422` empty reason |
| POST | `/ask` | `{"question": "..."}` (3–500 chars) | `200` answer, `grounded`, sources, scores | `422` |
| GET | `/metrics` | – | `200` dashboard numbers | – |
| GET | `/reports/documents.csv` | – | `200` CSV | – |

Responses never contain internal file paths or raw error text.

## Examples

```bash
# upload and process
curl -H "X-API-Key: $API_KEY" -F "file=@sample_docs/invoice_harbor.pdf" http://localhost:8000/documents

# search
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/documents?q=Harbor&status=Completed"

# ask a question
curl -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
     -d '{"question":"What is the total amount on invoice HL-310?"}' http://localhost:8000/ask

# reject with a reason
curl -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
     -d '{"reason":"Incomplete invoice"}' http://localhost:8000/documents/5/reject
```

Example `/ask` answer:

```json
{
  "answer": "According to **invoice_harbor.pdf**: Invoice No: HL-310; Total Amount: $800.00",
  "grounded": true,
  "sources": [{"document_id": 4, "filename": "invoice_harbor.pdf", "status": "Completed",
               "chunk_index": 0, "score": 0.351, "snippet": "Harbor Logistics Co INVOICE ..."}],
  "top_score": 0.351, "coverage": 1.0, "reason": "answered from retrieved document text"
}
```

When the documents do not contain the answer: `"grounded": false`, the answer is *"The available documents do not contain enough information to answer this question."* and `sources` is empty.

All 28 API behaviours above (including `401`, `409`, `413`, `415`, `422`, `404`) are checked by `test_e2e.py`.
