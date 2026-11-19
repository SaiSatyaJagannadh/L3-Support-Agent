"""Data access for tickets, comments and knowledge docs. Used by the agent graph, the API and the Streamlit UI so all three see the same rows."""
import os, re, uuid
from db import DB
from data import APPS, IMPACT, URGENCY

# ---- tickets ------------------------------------------------------------------
def next_number():
    return f"INC{(DB.execute('select max(cast(substr(number,4) as integer)) as n from tickets')[0]['n'] or 1000) + 1}"

def create_ticket(*, app, short, body, impact="team", source, thread="", idem=None, requester="demo.user"):
    """Insert a ticket (source = 'ai' or 'manual'). Assignment group comes from the rules table; with SN_INSTANCE set the incident is also created in ServiceNow."""
    if impact not in IMPACT: raise ValueError(f"impact must be one of {list(IMPACT)}")
    app = app if app in APPS else "unknown"
    with DB.l:
        row = DB.execute("select l2 from rules where app=?", (app,)).fetchone()
        grp = row["l2"] if row else "L2-Triage"                       # no rule -> triage group
        ex = DB.execute("select number,grp from tickets where idem=?", (idem or "",)).fetchone() if idem else None   # idempotent on draft id
        if ex: return ex["number"], ex["grp"]
        num = next_number()
        DB.execute("insert into tickets(number,idem,app,grp,short,body,state,source,impact,urgency,thread,requester) values(?,?,?,?,?,?,'new',?,?,?,?,?)",
                   (num, idem or str(uuid.uuid4()), app, grp, short, body, source, impact, URGENCY[impact], thread, requester))
        if os.getenv("SN_INSTANCE"):                                   # real ServiceNow Table API (SN_INSTANCE, SN_USER, SN_PASSWORD)
            import httpx
            base = os.getenv("SN_BASE") or f"https://{os.environ['SN_INSTANCE']}.service-now.com"
            r = httpx.post(f"{base}/api/now/table/incident", auth=(os.environ["SN_USER"], os.environ["SN_PASSWORD"]),
                           json={"short_description": short, "description": body, "assignment_group": grp, "correlation_id": idem or num}, timeout=20)
            r.raise_for_status(); sn = r.json()["result"]["number"]
            DB.execute("update tickets set number=? where number=?", (sn, num)); num = sn
        DB.commit()
    return num, grp

def list_tickets(state=None, source=None, q=None):
    sql, args = "select number,app,grp as 'group',short,state,source,impact,urgency,created_at from tickets where 1=1", []
    if state: sql += " and state=?"; args.append(state)
    if source: sql += " and source=?"; args.append(source)
    if q: sql += " and (short like ? or body like ? or number like ?)"; args += [f"%{q}%"] * 3
    return DB.rows(sql + " order by created_at desc, number desc", args)

def get_ticket(number):
    t = DB.rows("select number,app,grp as 'group',short,body,state,source,impact,urgency,requester,created_at from tickets where number=?", (number,))
    return {**t[0], "comments": DB.rows("select author,text,ts from ticket_comments where number=? order by id", (number,))} if t else None

def add_comment(number, text, author="demo.user"):
    if not text.strip(): raise ValueError("comment is empty")
    if not DB.execute("select 1 from tickets where number=?", (number,)): raise KeyError(number)
    DB.execute("insert into ticket_comments(number,author,text) values(?,?,?)", (number, author, text.strip())); DB.commit()

def set_state(number, state):
    if state not in ("new", "in_progress", "resolved"): raise ValueError("bad state")
    DB.execute("update tickets set state=? where number=?", (state, number)); DB.commit()

# ---- knowledge docs -------------------------------------------------------------
def list_docs():
    out = DB.rows("select id,source,app,title,url,acl,text,added_at from kb_docs order by rowid")
    for d in out: d["acl"] = d["acl"].split(",")
    return out

def add_doc(d):
    """Insert a doc (dict with text; id/source/app/title/url/acl optional). Used by ingestion, the paste form and the Google Doc import."""
    id_ = d.get("id") or f"doc-{uuid.uuid4().hex[:8]}"
    DB.execute("insert or replace into kb_docs(id,source,app,title,url,acl,text) values(?,?,?,?,?,?,?)",
               (id_, d.get("source", "manual"), d.get("app", "all"), d.get("title") or d["text"][:60], d.get("url", ""), ",".join(d.get("acl", ["staff"])), d["text"]))
    DB.commit(); return id_

def gdoc_export_url(url):
    m = re.match(r"https://docs\.google\.com/document/d/([\w-]+)", url.strip())
    if not m: raise ValueError("Only Google Docs links (https://docs.google.com/document/d/...) are supported")
    return f"https://docs.google.com/document/d/{m.group(1)}/export?format=txt"

def import_gdoc(url, app="all", fetch=None):
    """Import a Google Doc shared as 'anyone with the link'. No API key needed; private docs are refused. The text is stored as untrusted content."""
    import httpx
    r = (fetch or (lambda u: httpx.get(u, follow_redirects=True, timeout=15)))(gdoc_export_url(url))
    text = r.text
    if r.status_code != 200 or "text/plain" not in r.headers.get("content-type", "text/plain") or text.lstrip().startswith("<"):
        raise ValueError("Could not read the document. Set sharing to 'Anyone with the link can view' and try again.")
    text = text.strip()[:50000]
    if not text: raise ValueError("The document is empty")
    title = text.splitlines()[0].strip()[:80]
    return add_doc({"source": "google-docs", "app": app, "title": title, "url": url, "text": text})
