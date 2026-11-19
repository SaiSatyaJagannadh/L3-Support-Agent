# L3 Assist

An AI-assisted L3 support product. It answers from your documents with citations, asks follow-up questions until the problem is clear, checks logs and similar tickets, and raises a ticket **only after the user approves**. Tickets can also be created by hand, with no AI.

![Architecture](docs/architecture.png)

The full design is in [`L3SupportAgent-project.md`](L3SupportAgent-project.md). This repo is a working proof of concept: it runs with **no keys and no cloud accounts** on built-in sample data (three fictional apps, 15 runbooks, 8 sample tickets). Real systems plug in through environment variables.

## Run the demo

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py        # http://localhost:8501
```

Nothing else is needed. Try: click "PayFlow 504 timeout on disbursement" → answer the follow-up ("prod") → read the cited answer and **How I got this answer** → "Still stuck? Raise a ticket" → answer the impact question → review the draft → Submit.

## What you can show

| Page | What it does |
| --- | --- |
| 💬 Assistant | Chat with follow-up chips, streamed cited answers, a plain-English explanation of every answer, 👍/👎, AI-drafted tickets with similar-ticket matching and an approval step |
| 🎫 Tickets | Pre-created sample tickets plus anything you create. Filter by state or origin (AI / manual / sample), open a ticket, comment, change status, **New ticket** without AI |
| 📚 Knowledge | Browse the documents the current role may see, paste a new one, or import a public Google Doc by link |

The sidebar role picker ("Support staff" / "L3 engineer") shows access control: the L3-only runbook only appears for L3.

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (done: `SaiSatyaJagannadh/L3-Support-Agent`).
2. At [share.streamlit.io](https://share.streamlit.io) choose **Create app**, pick the repo and branch `main`, set the main file to `streamlit_app.py`, and deploy. Cloud installs the root `requirements.txt`.
3. Keys are optional. To add any, paste them under **Settings → Secrets** (format in `.streamlit/secrets.toml.example`).

Cloud storage is temporary, so the SQLite database resets to the sample data whenever the app restarts, and all visitors share one database.

## Data

SQLite file `l3.db` (created on first run; delete it to reset). Tables: `tickets` (source `ai` / `manual` / `seed`), `ticket_comments`, `kb_docs`, `conversations`, `messages`, `rules` (ticket routing), `logs`, `feedback`, `unanswered` (knowledge gaps), `audit`. Sample documents live in `poc/kb/*.md`.

## Keys (all optional)

Copy `.env.example` to `.env`. With nothing set, answers quote the best-matching document text. See [`POC-NOTES.md`](POC-NOTES.md) for what each key turns on.

## Checks

```bash
cd poc && pip install -r requirements.txt
python3 -m pytest -q        # agent, API, database and Streamlit UI tests
python3 evals.py            # answer quality and safety gate
python3 redteam.py          # PyRIT attacks
python3 dummy_run.py        # integrations against local mock services
```

`./run_poc.sh` runs all of the above plus the Docker build and the Helm/Bicep checks.

## Layout

| Path | What |
| --- | --- |
| `streamlit_app.py` | The UI (runs the agent in-process) |
| `poc/core.py` | LangGraph agent: guardrails, retrieval, answers, ticket flow |
| `poc/db.py`, `poc/store.py` | SQLite schema, seed data, ticket/document data access |
| `poc/kb/`, `poc/data.py` | Sample documents, tickets, routing rules, eval sets |
| `poc/main.py` | Optional REST API over the same agent and store |
| `infra/`, `Dockerfile`, `.gitlab-ci.yml` | Helm, Bicep, container and CI |
