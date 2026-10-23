# CT-200 QA Traceability API

FastAPI service that extracts the supplied CT-200 manual PDFs into a versioned hierarchy, stores version-pinned selections, generates structured QA test ideas through an OpenAI-compatible LLM endpoint, and reports whether generated tests have become stale.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY='...'
uvicorn app.main:app --reload
```

Set `OPENAI_BASE_URL` and `OPENAI_MODEL` for another OpenAI-compatible provider, or set `GROQ_API_KEY` and post `{"provider":"groq"}` to generation. SQLite is stored at `./ct200.db`; `DATABASE_URL` may override it. Generated LLM content and immutable source snapshots are stored in SQLite as a justified JSON document store for this single-user assignment.

## Ingest both versions

```powershell
curl -X POST 'http://127.0.0.1:8000/documents/ingest?path=C:/path/ct200_manual.pdf'
curl -X POST 'http://127.0.0.1:8000/documents/ingest?path=C:/path/ct200_manual_v2.pdf'
curl 'http://127.0.0.1:8000/documents/ct200-manual/sections?version=1'
curl 'http://127.0.0.1:8000/documents/ct200-manual/sections?version=2'
```

The version number is assigned sequentially. PDFs are read directly; no intermediate Markdown is used. Ingestion requires a readable local PDF path.

## Version/staleness walkthrough

1. Ingest v1 and v2 as above. V2 revises battery capacity and low-battery threshold, cuff pressure increments, E3 response time, alarm code coverage, and adds E6 and data export.
2. Search e.g. `/documents/ct200-manual/search?q=Battery%20Life&version=1`, then fetch a specific node with `/nodes/{node_id}`.
3. Create a pinned selection: `POST /selections` with `{"name":"Battery requirements","node_ids":["<v1-node-id>"],"version":1}`.
4. `POST /selections/{selection_id}/generate` with `{}` to create 3–5 validated test ideas. Configure an API key first.
5. `GET /generations?selection_id={selection_id}` returns the saved cases and live staleness status. Older selection text remains retrievable from its snapshot after re-ingestion.
6. `GET /nodes/{logical_id}/changes` is not the change route; use `GET /nodes/{node_id}/changes` for version history and diff summary. `GET /generations?node_id={node_id}` retrieves affected generations.

Interactive API docs: `/docs`.
