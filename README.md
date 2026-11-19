# Support Assist

An AI-assisted support desk. It answers from your documents with citations, asks follow-up questions until the problem is clear, checks logs and similar tickets, and raises a ticket **only after the user approves**. Tickets can also be created by hand, with no AI, and both kinds live in one ticketing system with SLA tracking, attachments and L2 → L3 escalation.

![Architecture](docs/architecture.png)

The full design is in [`L3SupportAgent-project.md`](L3SupportAgent-project.md). This repo is a working proof of concept that runs with **no keys and no cloud accounts** on built-in sample data (three fictional apps, 15 runbooks, 11 sample tickets). Real systems plug in through secrets.

## Run the demo

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py        # http://localhost:8501
```

Try: click "PayFlow 504 timeout on disbursement" → answer the follow-up ("prod") → read the cited answer and **How I got this answer** → "Still stuck? Raise a ticket" → say who is affected → review the draft, add an attachment, pick Incident or User request → Submit.

## Pages

| Page | What it does |
| --- | --- |
| 💬 **Assist** | Chat with follow-up chips and streamed, cited answers. Attach logs or screenshots in the chat box. If nothing in the documents matches, it asks whether you want to add more detail (attach a log) or have a ticket created. 👍/👎, an explanation on every answer, and an AI-drafted ticket with similar-ticket matching and an approval step |
| 📊 **Dashboard** | Open tickets, P1 open, SLA at risk / breached, how many chats the assistant resolved without a ticket, charts, an SLA watchlist and "reported by me" |
| 🎫 **Tickets** | Sample tickets plus anything you create. Filter by type, state, origin (AI / manual / sample) or "reported by me". Open a ticket: details, activity timeline, attachments (download / add), related knowledge and similar tickets. Change status, **resolve with a fix note**, **escalate to L3** with a hand-off note, **publish the fix to the knowledge base** |
| ➕ **New ticket** | A separate page for creating a ticket by hand: type (Incident `INC` or User request `UR`), application, environment, description, who is affected (sets the priority) and attachments |
| 📚 **Knowledge** | Browse the documents your profile may see, paste a new one, or import a public Google Doc by link |

**Ticket numbers** are always 10 characters: `INC` + 7 digits (e.g. `INC0010009`) for incidents, `UR` + 8 digits (e.g. `UR00020004`) for user requests. **Priority** follows the impact: everyone P1 (4 h target), team P2 (8 h), just me P3 (24 h). **Attachments**: up to 5 files of 5 MB each (images, PDF, text/log/CSV/JSON/Markdown, Word, Excel); type and size are checked and a bad file creates no ticket.

The sidebar shows who you are (Priya Nair, Support analyst, or Arjun Rao, L3 engineer; use *Switch user*) and a **System status** panel listing what each part runs on (database type, AI model, search, ticketing, safety checks, sign-in) with a **Test AI connection** button.

## AI key and deploy

No key is needed. To get written answers instead of quoted document text, add `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, default `gpt-4o-mini`) to:
- **Streamlit Cloud:** app → Settings → Secrets (format in `.streamlit/secrets.toml.example`)
- **Local:** copy `.env.example` to `.env`

Deploy: share.streamlit.io → Create app → this repo, branch `main`, main file `streamlit_app.py`. It redeploys on every push. Cloud storage is temporary, so the database resets to the sample data when the app restarts, and all visitors share one database.

## Data

SQLite file `l3.db` (created on first run; delete it to reset). Tables: `tickets` (type, source, urgency, requester), `ticket_comments` (comments and activity events), `attachments`, `kb_docs`, `conversations`, `messages`, `rules` (routing), `logs`, `feedback`, `unanswered` (knowledge gaps), `audit`. Sample documents live in `poc/kb/*.md`.

## Checks

```bash
cd poc && pip install -r requirements.txt
python3 -m pytest -q        # agent, API, database, SLA, attachments and Streamlit UI tests
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
| `poc/db.py`, `poc/store.py`, `poc/health.py` | SQLite schema and seed data; ticket / attachment / SLA / document logic; system status |
| `poc/kb/`, `poc/data.py` | Sample documents, tickets, users, routing rules, eval sets |
| `poc/main.py` | Optional REST API over the same agent and store |
| `infra/`, `Dockerfile`, `.gitlab-ci.yml` | Helm, Bicep, container and CI |
