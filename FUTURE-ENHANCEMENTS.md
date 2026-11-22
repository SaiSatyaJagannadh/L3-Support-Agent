# Future enhancements

What is not built yet in Support Assist, grouped by theme and roughly ordered by value. The "Not built" list in `README.md` and `L3SupportAgent-project.md` is the source; this file expands it into a backlog.

## 1. Security and access (do first)

- **Server-side role enforcement.** Roles are enforced in the UI only (`streamlit_app.CAN`). Enforce them in `store.py` and the REST API so a direct call cannot bypass them.
- **Real sign-in.** Replace the four demo users with Entra ID (token validation already exists in `poc/auth.py`); map Entra groups to `everyone` / `staff` / `l3`.
- **SharePoint / Confluence ACL mapping** so document entitlements follow the source system instead of a manually chosen group.
- **Network hardening.** VNet, private endpoints and WAF in the Bicep skeleton; APIM in front of the API.

## 2. Integrations

- **Run against the real services.** Azure OpenAI, Azure AI Search, Prompt Shields, ServiceNow, Confluence and Entra are coded and mock-tested only.
- **ServiceNow status sync** so ticket state in Support Assist follows the source of truth.
- **OneNote and GitLab crawlers** (Confluence crawler exists in `poc/ingestion.py`).
- **MCP servers / APIM** exposing the agent's tools to other clients.

## 3. Agent capabilities

- **Read text from images and PDFs** attached to chats and tickets (OCR / document intelligence).
- **Email intake and notifications** (new ticket, SLA at risk, escalation, resolution).
- **Better retrieval:** vector or hybrid search instead of keyword scoring; re-ranking; freshness signals.
- **Persistent graph state** with a SQL Server checkpointer, so conversations survive restarts and scale past one process.

## 4. Product and UX

- **Admin screen** (only the `/admin/summary` API remains): manage routing rules, users, entitlements and knowledge sources.
- **Dashboard depth:** trends over time, deflection rate, time to resolve, feedback (👍/👎) analysis, unanswered-question backlog.
- **Accessibility testing** and fixes (keyboard, screen reader, contrast).

## 5. Quality and operations

- **Run the GitLab pipeline** for real and deploy the Helm chart to a cluster.
- **Grow the eval sets** (golden and adversarial) and track scores per release.
- **Observability:** tracing, cost and latency metrics, alerting.
- **Scale tests** beyond the current load test, on a real database.
