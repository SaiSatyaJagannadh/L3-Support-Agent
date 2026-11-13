# L3 Support Agent

An L3 support assistant that answers from indexed docs with citations, asks follow-up questions until the issue is clear, checks logs and similar tickets, and creates a ServiceNow ticket only after the user confirms. The full design is in [`L3SupportAgent-project.md`](L3SupportAgent-project.md).

This repo holds a **local proof of concept**. It runs with no cloud accounts: everything that would need Azure, ServiceNow, Confluence or Entra has a local stand-in or a mock.

## How it works

```
user message -> intake (PII redaction, injection check) -> triage (app / env follow-ups, max 3)
  -> knowledge (answer with citations, access-filtered)
  -> "still stuck": log insights -> similar tickets -> ticket draft
  -> user approval -> create ticket, routed by a rules table
```

LangGraph runs the flow in `poc/core.py`. The approval step is a graph interrupt, so nothing is written to the ticket table until the user confirms.

## Quick start

Needs Python 3.12 and Node 20+. Docker, `helm` and `az` are only needed for the infra checks.

```bash
cd poc
pip install -r requirements.txt
python3 -m uvicorn main:app --port 8000    # API + simple UI at http://localhost:8000
```

React UI (separate terminal):

```bash
cd apps/web && npm install && npm run dev  # http://localhost:5173
```

Try: "PayFlow 504 timeout" -> answer "prod" -> "Still stuck? Raise a ticket" -> Submit.

## Checks

```bash
cd poc
python3 -m pytest -q --ignore=test_e2e.py   # unit tests
python3 evals.py                            # golden + adversarial eval gate
python3 redteam.py                          # PyRIT converter attacks
python3 dummy_run.py                        # integrations against local mock services
```

`./run_poc.sh` chains the test, build and manifest-validation stages.

## Layout

| Path | What |
| --- | --- |
| `poc/` | FastAPI app, LangGraph agent, synthetic data, tests, evals, red team, load test |
| `apps/web/` | React + TypeScript + Fluent UI + MSAL front end |
| `infra/` | Bicep skeleton, Helm chart, Kubernetes manifest |
| `.gitlab-ci.yml` | Test (with eval gate), build, deploy stages |
| `POC-NOTES.md` | What was built, stand-ins, and every key to add for real services |
| `CLAUDE.md` | Guidance for Claude Code working in this repo |

## Using real services

Set the environment variables listed in [`POC-NOTES.md`](POC-NOTES.md) (copy `poc/.env.example`) for Azure OpenAI, Entra, Prompt Shields, Azure AI Search, ServiceNow and Confluence. With none set, the POC answers from local docs and stores tickets in SQLite.

## Status

Verified locally: unit tests, eval gate, red team, browser test, load test, dummy-service integration checks, Docker build, `helm lint`, `az bicep build`. Not done: Azure SQL (SQLite stands in), deploying to a cluster, running the GitLab pipeline, and any run against the real vendor services.
