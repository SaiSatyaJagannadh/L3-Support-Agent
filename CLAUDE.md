# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local proof of concept of the L3 support agent designed in `L3SupportAgent-project.md` (the architecture spec; its last section, "POC status", lists what is built vs stubbed). `POC-NOTES.md` has the env-var/key list. Nothing is deployed; nothing needs real accounts to run.

## Commands

Run from `poc/` unless noted. Install: `pip install -r requirements.txt` (Python 3.12; includes pyrit, which is large).

```
python3 -m pytest -q --ignore=test_e2e.py     # unit tests
python3 -m pytest -q test_poc.py::test_acl_trimming_and_injection   # single test
python3 evals.py                               # golden + adversarial gate (exit 1 if below threshold)
python3 redteam.py                             # PyRIT converter attacks against the graph in-process
python3 dummy_run.py                           # starts local mock Azure/ServiceNow/Confluence/Entra/etc on :9000 and exercises the real integration code paths
python3 -m uvicorn main:app --port 8000        # API + plain HTML UI at /
python3 loadtest.py http://localhost:8000 100  # needs server running
python3 pyrit_attack.py                        # real PyRIT attack run; needs server on :8000
python3 -m pytest -q test_e2e.py               # Playwright; needs server on :8000 and `playwright install chromium`
```

React UI: `cd apps/web && npm install && npm run dev` (:5173, proxies to :8000); `npm run build` type-checks.
Infra checks (repo root): `helm lint infra/helm`, `helm template infra/helm`, `az bicep build --file infra/main.bicep --stdout`, `docker build poc`. `./run_poc.sh` chains the test/build/validate stages (macOS has no `timeout` binary).

## Architecture

Everything backend lives in `poc/core.py`: one LangGraph `StateGraph` (state `S`) compiled with an in-memory checkpointer, plus the helpers it calls (redaction, search, LLM, SQLite audit/tickets/rules). `main.py` is a thin FastAPI wrapper; `core.run(thread, **inp)` is the single entry point used by the API, `evals.py` and `redteam.py`.

Graph routing: `START` → `intake` (PII redact, injection check) → `triage` (slot filling for app/env, max 3 clarify turns, ends the turn with a question) → `knowledge` (cited answer). A separate `action="not_solved"` entry goes `logs` → `similar` → `draft` → `approve` → `create`. `approve` calls `interrupt()`; the API returns `status: needs_approval` and `POST /confirm` resumes with `Command(resume=...)` (create / cancel / link). Nothing is written to the ticket table before that resume. Ticket assignment comes from the `rules` table, never the LLM; creation is idempotent on the draft id.

Integrations are env-gated inside `core.py`/`auth.py`/`ingestion.py` and fall back to local behaviour when unset: Azure OpenAI (`answer`), Azure AI Search (`search_azure`), Prompt Shields (`shielded`), ServiceNow Table API (in `create`, `SN_BASE` overrides the host), Confluence crawl, Entra JWT (`auth.user`, `AAD_AUTHORITY` overrides the host). Unset means: extractive answer, in-memory token-overlap search over `data.KB`, regex injection check, local `tickets` table, header-based identity (`X-User-Groups`, `X-User-Roles`). `dummy_run.py` flips all of these on against local mocks.

## Gotchas

- `_t` (thread id) is a field in the graph state `S` on purpose: nodes use it for audit/unanswered logging. Callers pass it as `_t=` to `core.run`; `main.chat` does this.
- State is global per process: `core.DB` is one shared in-memory SQLite connection (wrapped in `_DB` with a lock, `execute` returns fully fetched rows), and tests share it. `test_decline_creates_nothing` expects the ticket created by the earlier test to exist, so test order matters.
- `data.KB` is mutated by `ingestion.run` and read by the mocks in `dummy_run.py`; ACL is by group name in each doc's `acl` list. One doc is deliberately L3-only and one deliberately contains an injection string; `search` must never return them to `staff`.
- Retrieval confidence threshold (0.3 overlap) decides "answer" vs "no documented answer"; changing `data.py` docs or `GOLDEN` can break `evals.py` thresholds.
- PyRIT 1.1.0 moved modules (`pyrit.converter`, not `pyrit.prompt_converter`); attack outcomes report UNDETERMINED because no scoring LLM is configured, so pass/fail is judged from API state.
- Auth stays in dev-header mode unless `AAD_TENANT_ID` is set, in which case every route using `Depends(user)` needs a valid bearer token.
