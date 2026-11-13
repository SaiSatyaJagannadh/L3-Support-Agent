# L3 Support Agent — POC notes

## What I built (`poc/`)
Runs fully locally, no keys needed. Nothing was committed or pushed.

| File | What |
| --- | --- |
| `poc/core.py` | LangGraph graph: intake (PII redact + injection block) → triage (asks follow-ups for app/env, max 3) → knowledge (cited answer, ACL-trimmed search) → on "not solved": similar tickets → draft → **approval interrupt** → create ticket (idempotent, routed by rules table). Also SQLite audit/tickets/rules. |
| `poc/main.py` | FastAPI: `POST /chat`, `POST /confirm`, `GET /tickets`, `GET /` (UI) |
| `poc/data.py` | Synthetic data: 3 fake apps, 5 KB docs (one L3-only, one poisoned), 3 tickets, routing rules |
| `poc/static/index.html` | Minimal chat UI (plain HTML/JS): chat, citations, 👍/👎, ticket draft + Submit/Cancel/"Same as INC", My tickets, Admin |
| `poc/evals.py` | Golden-set eval gate (recall@3, citation accuracy, routing); `python3 evals.py` exits non-zero if below threshold |
| `poc/Dockerfile`, `infra/k8s.yaml` | Container + minimal AKS manifest |
| `poc/test_poc.py` | 5 tests: full flow, decline, ACL + injection, log insights/admin/evals, OneNote+GitLab sources |

## Run it
```
cd poc
pip install -r requirements.txt
python3 -m pytest -q                 # 3 pass
python3 -m uvicorn main:app --port 8000   # open http://localhost:8000
```
Try: "PayFlow 504 timeout" → answer "prod" → "Still stuck? Raise a ticket" → Submit.

## Keys / things YOU need to add (all optional for the POC)
Copy `poc/.env.example` to `.env` and export (`set -a; source .env; set +a`) before starting uvicorn:
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (+ `AZURE_OPENAI_API_VERSION`) → real GPT answers. Without them answers are the top matching doc text.
- `AAD_TENANT_ID`, `AAD_CLIENT_ID` (backend) and `VITE_AAD_TENANT_ID`, `VITE_AAD_CLIENT_ID` (web) → Entra sign-in + token validation.
- `CONTENT_SAFETY_ENDPOINT`, `CONTENT_SAFETY_KEY` → Azure Prompt Shields.
- `SN_INSTANCE`, `SN_USER`, `SN_PASSWORD` → create real ServiceNow incidents (otherwise local table).
- `CONFLUENCE_URL`, `CONFLUENCE_USER`, `CONFLUENCE_TOKEN`, `CONFLUENCE_SPACE` → ingestion crawls real Confluence.
- Not needed for the POC, needed for real build: Entra app registration (MSAL/JWT), Azure AI Search, Azure SQL, ServiceNow instance + OAuth, Confluence/GitLab/SharePoint tokens, Prompt Shields (Content Safety key), APIM.

## POC stand-ins (swap later)
| Spec says | POC does |
| --- | --- |
| React + Fluent UI + MSAL, SSE | `apps/web` (Vite + React + TS + Fluent UI v9 + MSAL React): builds and passes a browser e2e against the API. MSAL activates with `VITE_AAD_CLIENT_ID` + `VITE_AAD_TENANT_ID`, and the backend (`poc/auth.py`) validates the Entra JWT (signature, audience, issuer) when `AAD_TENANT_ID` + `AAD_CLIENT_ID` are set (verified: no/invalid token → 401; a valid Entra token is untested). `POST /chat/stream` provides SSE streaming; the UI uses the non-streaming endpoint. The old `poc/static/index.html` still works too. |
| Azure AI Search hybrid | Token-overlap scoring over in-memory docs |
| Azure OpenAI | Used if env vars set, else extractive fallback |
| Azure SQL + MSSQL checkpointer | SQLite (in-memory by default; set `POC_DB=file.db`) + LangGraph `MemorySaver` |
| MCP servers / APIM / ServiceNow | Local SQLite `tickets` table acts as GSNOW |
| Prompt Shields | Regex, plus real Prompt Shields call when `CONTENT_SAFETY_ENDPOINT` + `CONTENT_SAFETY_KEY` are set (untested against Azure) |
| Log insights (KQL/SPL templates) | Read-only templated filter over synthetic logs, attached to the ticket draft |
| OneNote / GitLab / Confluence / SharePoint crawlers | Synthetic docs tagged with those sources, no crawlers |
| Admin (`L3.Admin`) | `/admin/summary` gated by `X-User-Roles` header: feedback, unanswered questions, eval scores |
| Bicep/Helm/GitLab CI | `infra/main.bicep` (OpenAI, Search, KV, SQL, APIM skeleton; VNet/private endpoints/WAF omitted), `infra/helm/`, `.gitlab-ci.yml` (test+eval gate → build → dev → manual prod). **Written, not deployed or linted against real Azure/GitLab.** |
| PyRIT red team | `pip install pyrit` (1.1.0); `poc/redteam.py` uses PyRIT's Base64/ROT13/leetspeak converters to mutate attacks against the graph: 12 attacks, 0 failures, 0 tickets. Full PyRIT attack orchestration needs a target-LLM key. Plus the adversarial set in `evals.py`. |
| Playwright e2e | `poc/test_e2e.py` written (auto-skips unless `pip install playwright`); I verified the flow manually in Chrome instead |
| Load test | `poc/loadtest.py` (100 requests, 10 threads: 100/100 ok, p95 ≈ 530 ms locally) instead of Azure Load Testing |
| Ingestion worker | `poc/ingestion.py`: heading chunker + Confluence REST crawler, enabled by env vars below; not exercised against a real Confluence |
| ServiceNow | Real Table API create in `core.py`, enabled by env vars below; not exercised against a real instance |

Add the above when you need them; say which and I'll do it. Open questions in the project md are still yours to answer.

Verified in a real browser: chat → clarify → cited answer → draft → Submit → INC created → My tickets → Admin.

## Verified locally (final)
- 5 pytest tests, eval gate (incl. adversarial set), Playwright e2e (`test_e2e.py`, passes against a running server), load test 100/100.
- `infra/main.bicep` compiles (`az bicep build`); `.gitlab-ci.yml` and `infra/k8s.yaml` parse; the Docker image builds.
- Not verifiable without your accounts: deploying Bicep/Helm, running the GitLab pipeline, live Azure OpenAI/ServiceNow/Confluence calls, Entra sign-in (MSAL), Azure AI Search, Prompt Shields, PyRIT. Those need the keys/tenant listed above; I can't enter credentials for you.

## React UI
```
cd apps/web && npm install && npm run dev   # http://localhost:5173, proxies to API on :8000
```
Helm chart: `helm lint infra/helm` passes.
Red team: `python3 redteam.py`.

## Dummy-service run (no accounts needed)
`python3 dummy_run.py` starts local fake Azure OpenAI, ServiceNow, Content Safety (Prompt Shields), Confluence and Entra (JWKS + signed JWTs), sets the env vars from this doc to point at them, and runs the real code paths: valid/forged/wrong-audience tokens (200/401/401), Azure OpenAI answer path, Prompt Shields block, Confluence crawl→index→search, ServiceNow create → INC number, admin role from token claims. Also Azure AI Search REST path (`AZURE_SEARCH_ENDPOINT`/`AZURE_SEARCH_KEY`) with ACL filter. **9/9 pass.**
This proves our wiring and request shapes against fakes I wrote; it does not prove the real Azure/ServiceNow/Confluence/Entra services accept them. Swap in real values later with no code change (except the `*_BASE`/`AAD_AUTHORITY` overrides, which default to the real hosts).
PyRIT: `python3 pyrit_attack.py` (server on :8000) runs real PyRIT `PromptSendingAttack` with Base64/ROT13 converters through an `HTTPTarget` at the API: 9 attacks, 0 tickets written (outcome is UNDETERMINED because no scoring LLM is configured; pass = nothing written/leaked).
Still not run: Azure SQL (SQLite stand-in; no SQL adapter written), Bicep/Helm deploy (no cluster/subscription; `az bicep build` and `helm lint` pass), GitLab pipeline (running it locally via `gitlab-ci-local` was blocked by the permission classifier; run `npx gitlab-ci-local test` yourself if you want it).

CI `test` stage commands (pytest + eval gate) were run by hand locally and pass; `helm template` renders 2 resources. The pipeline itself has not run on GitLab.

## POC scope: accepted dummies (decided with you)
For this POC these stand-ins are the agreed substitutes, not gaps to close:
| Spec item | POC substitute |
| --- | --- |
| Azure SQL | SQLite (same tables; swap to a SQL Server driver when an instance exists) |
| AKS / Bicep deploy | `helm lint`, `helm template`, `az bicep build`, Docker build (no cluster) |
| GitLab pipeline | `./run_poc.sh` runs the same stages locally (test, build, render/validate) |
| Azure OpenAI, AI Search, Prompt Shields, ServiceNow, Confluence, Entra | local mocks in `poc/dummy_run.py` (9/9 checks) |
| PyRIT scoring | no scoring LLM; pass = nothing written or leaked, checked via the API |

**Run everything with one command:** `./run_poc.sh` (needs Docker running, `helm`, `az`).
