# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local proof of concept of the L3 support agent designed in `L3SupportAgent-project.md` (its last section, "POC status", lists what is built vs stubbed). `README.md` is the entry point; `POC-NOTES.md` has the demo script, keys and deploy steps. Nothing needs real accounts or keys to run.

## Commands

Run from the repo root unless noted. `pip install -r requirements.txt` runs the app; `pip install -r poc/requirements.txt` adds API/test/red-team deps (pyrit is large).

```
streamlit run streamlit_app.py                 # the UI, http://localhost:8501 (also the Streamlit Cloud entry point)
cd poc && python3 -m pytest -q                 # all tests (agent, API, DB, Streamlit UI via AppTest)
cd poc && python3 -m pytest -q test_poc.py::test_link_adds_comment_instead_of_duplicate   # single test
cd poc && python3 evals.py                     # golden + adversarial gate (exit 1 if below threshold)
cd poc && python3 redteam.py                   # PyRIT converter attacks against the graph in-process
cd poc && python3 dummy_run.py                 # local mock Azure/ServiceNow/Confluence/Entra on :9000; exercises the real integration code paths
cd poc && python3 -m uvicorn main:app --port 8000   # optional REST API
cd poc && python3 pyrit_attack.py              # real PyRIT attack run; needs the API on :8000
./run_poc.sh                                   # tests + evals + red team + mocks + docker build + helm/bicep checks
```

Reset the demo database by deleting `l3.db`. Regenerate the architecture image: render `docs/architecture.html` with Playwright to `docs/architecture.png`.

## Architecture

`streamlit_app.py` (product name "Support Assist"; pages Assist, Dashboard, Tickets, New ticket, Knowledge) runs the agent in-process (no API needed). It calls `core.run(thread, _t=..., groups=..., message=... | action="not_solved" | resume=...)`, the single entry point also used by `main.py` (FastAPI), `evals.py` and `redteam.py`.

- `poc/db.py`: SQLite connection (`POC_DB`, default `l3.db`; `:memory:` in tests), schema (versioned with `SCHEMA_VERSION`; an older demo DB is dropped and re-seeded, so bump it when changing tables), seed data, tiny `.env` loader. `DB.execute` returns fully fetched rows (`sqlite3.Row`), `DB.rows` returns dicts.
- `poc/store.py`: all ticket / comment / attachment / document access (`create_ticket`, `escalate`, `resolve`, `promote_to_kb`, `sla`, `add_attachment`, `import_gdoc`, ...). Ticket numbers are 10 characters (`INC`+7 digits, `UR`+8); SLA is P1 4h / P2 8h / P3 24h; attachments are validated by extension and size before anything is written. The agent, API and UI all go through it so AI-created and manual tickets live in one `tickets` table (`source` = `ai` / `manual` / `seed`).
- `poc/health.py`: the System status rows and the live AI ping used by the sidebar.
- `poc/core.py`: guardrails, retrieval, LLM answer, and one LangGraph `StateGraph` with an in-memory checkpointer. Chat path: `intake → triage → knowledge`. `action="not_solved"` path: `collect → logs → similar → draft → approve → create`. `approve` calls `interrupt()`; the caller resumes with `Command(resume={decision: create|cancel|link})`. Nothing is written to `tickets` before that resume. Priority comes from `data.URGENCY[impact]` and the assignment group from the `rules` table, never the LLM.
- Every node appends plain-English lines to `trace`, which the UI shows as "How I got this answer". Keep that in sync when changing node behaviour.
- Knowledge docs are Markdown files with front matter in `poc/kb/` (loaded by `data.py`, seeded into `kb_docs`).

Integrations are env-gated and fall back to local behaviour when unset: Azure OpenAI (`core.answer`), Azure AI Search (`core.search_azure`), Prompt Shields (`core.shielded`), ServiceNow (`store.create_ticket`, `SN_BASE` overrides the host), Confluence crawl (`ingestion.py`), Entra JWT (`auth.user`, `AAD_AUTHORITY` overrides the host). `dummy_run.py` switches them all on against local mocks. Streamlit secrets are copied into `os.environ` at startup. A plain `OPENAI_API_KEY` (model from `OPENAI_MODEL`, default `gpt-4o-mini`) is supported in `core.answer` alongside Azure OpenAI.

## Gotchas

- `_t` (thread id) is a field of the graph state `S` on purpose; callers must pass it.
- Graph state persists per thread, so stale values leak into later turns. `core.run` therefore returns citations only when `status == "answered"`; the draft still reads the saved citations internally. `want_ticket` / `awaiting` route a reply to the pending ticket follow-up, and a reply that doesn't answer it is treated as a new question.
- State is global per process: `core.DB` is one shared connection and `core` is imported once, so Streamlit visitors and tests share data. `conftest.py` sets `POC_DB=:memory:` before any import; tests assert counts relative to before, not absolute (seed data is 11 tickets: INC0010001-8 and UR00020001-3).
- Retrieval needs at least two matching key terms (`terms()` drops stopwords and app/env names); app-specific docs are filtered by the detected app, `all` docs match any app. Changing `poc/kb/*.md` or `data.GOLDEN` can break `evals.py` thresholds and `test_poc.py` assertions on doc ids.
- Seed ticket ages are relative to now, so SLA tests (`INC0010004` breached, `INC0010006` at risk, `INC0010005` on track) hold only for a freshly created database.
- Two documents are test fixtures: `kb4` (L3-only, must never reach `staff`) and `kb5` (contains an injection string, must never be returned).
- Streamlit `AppTest` keeps stale elements after `st.rerun()` in its tree; assert on `at.session_state` or real-browser behaviour for "this disappeared" checks.
- PyRIT 1.1.0 moved modules (`pyrit.converter`); attack outcomes are UNDETERMINED without a scoring LLM, so pass/fail is judged from app state.
- The earlier React UI (`apps/web`) and plain HTML page were removed; they remain in git history.
