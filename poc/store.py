"""Data access for tickets, comments, attachments and knowledge docs. Used by the agent graph, the API and the Streamlit UI so all three see the same rows."""
import os, re, uuid, datetime as dt
from db import DB
from data import APPS, IMPACT, URGENCY, TYPES, SLA_HOURS, RULES

STATES = ("new", "in_progress", "resolved")
NUMBER_BASE = {"INC": 10000, "UR": 20000}          # first number issued per type: INC0010001, UR00020001
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".txt", ".log", ".csv", ".json", ".md", ".docx", ".xlsx"}
MAX_FILE_BYTES, MAX_FILES = 5 * 1024 * 1024, 5
now = lambda: dt.datetime.now(dt.timezone.utc)
stamp = lambda: now().strftime("%Y-%m-%d %H:%M:%S")      # UTC, same format SQLite's CURRENT_TIMESTAMP uses

# ---- tickets ------------------------------------------------------------------
def next_number(kind="INC"):
    """ServiceNow-style number, always 10 characters: INC + 7 digits, or UR + 8 digits."""
    if kind not in TYPES: raise ValueError(f"type must be one of {list(TYPES)}")
    cur = DB.execute("select max(cast(substr(number, ?) as integer)) as n from tickets where number like ? and length(number)=10", (len(kind) + 1, kind + "%"))[0]["n"]
    return f"{kind}{(cur or NUMBER_BASE[kind]) + 1:0{10 - len(kind)}d}"

def add_event(number, text, author="System"):
    DB.execute("insert into ticket_comments(number,author,text,kind) values(?,?,?,'event')", (number, author, text))
    DB.execute("update tickets set updated_at=? where number=?", (stamp(), number))

def create_ticket(*, app, short, body, impact="team", source, thread="", idem=None, requester="demo.user", type="INC", attachments=()):
    """Insert a ticket (source = 'ai' or 'manual'). Assignment group comes from the rules table; with SN_INSTANCE set the incident is also created in ServiceNow.
    attachments: iterable of (filename, bytes). Returns (number, group)."""
    if impact not in IMPACT: raise ValueError(f"impact must be one of {list(IMPACT)}")
    if type not in TYPES: raise ValueError(f"type must be one of {list(TYPES)}")
    app = app if app in APPS else "unknown"
    files = [validate_upload(n, len(b)) and (n, b) for n, b in attachments]       # validate everything before writing anything
    if len(files) > MAX_FILES: raise ValueError(f"At most {MAX_FILES} attachments per ticket")
    with DB.l:
        row = DB.execute("select l2 from rules where app=?", (app,)).fetchone()
        grp = row["l2"] if row else "L2-Triage"                       # no rule -> triage group
        ex = DB.execute("select number,grp from tickets where idem=?", (idem,)).fetchone() if idem else None   # idempotent on draft id
        if ex: return ex["number"], ex["grp"]
        num = next_number(type)
        DB.execute("insert into tickets(number,type,idem,app,grp,short,body,state,source,impact,urgency,thread,requester) values(?,?,?,?,?,?,?,'new',?,?,?,?,?)",
                   (num, type, idem or str(uuid.uuid4()), app, grp, short, body, source, impact, URGENCY[impact], thread, requester))
        if os.getenv("SN_INSTANCE"):                                   # real ServiceNow Table API (SN_INSTANCE, SN_USER, SN_PASSWORD)
            import httpx
            base = os.getenv("SN_BASE") or f"https://{os.environ['SN_INSTANCE']}.service-now.com"
            r = httpx.post(f"{base}/api/now/table/incident", auth=(os.environ["SN_USER"], os.environ["SN_PASSWORD"]),
                           json={"short_description": short, "description": body, "assignment_group": grp, "correlation_id": idem or num}, timeout=20)
            r.raise_for_status(); sn = r.json()["result"]["number"]
            DB.execute("update tickets set number=? where number=?", (sn, num)); num = sn
        add_event(num, f"{TYPES[type]} created by {requester} ({'AI-assisted' if source == 'ai' else 'manual'}), assigned to {grp}", requester)
        for n, b in files: add_attachment(num, n, b)
        DB.commit()
    return num, grp

def sla(t):
    """Resolution target by priority (P1 4h, P2 8h, P3 24h). Returns label, state (met/on track/at risk/breached) and hours left."""
    hours = SLA_HOURS[t["urgency"]]; created = dt.datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    left = hours - (now() - created).total_seconds() / 3600
    if t["state"] == "resolved": return {"state": "met", "label": "✅ Closed", "hours_left": left}
    if left <= 0: return {"state": "breached", "label": f"🔴 Breached {abs(left):.0f}h ago", "hours_left": left}
    if left <= hours * 0.25: return {"state": "at risk", "label": f"🟠 At risk · {left:.1f}h left", "hours_left": left}
    return {"state": "on track", "label": f"🟢 {left:.0f}h left", "hours_left": left}

def list_tickets(state=None, source=None, q=None, requester=None, type=None):
    sql, args = "select number,type,app,grp as 'group',short,state,source,impact,urgency,requester,created_at,updated_at from tickets where 1=1", []
    for col, v in (("state", state), ("source", source), ("requester", requester), ("type", type)):
        if v: sql += f" and {col}=?"; args.append(v)
    if q: sql += " and (short like ? or body like ? or number like ?)"; args += [f"%{q}%"] * 3
    return DB.rows(sql + " order by created_at desc, number desc", args)

def get_ticket(number):
    t = DB.rows("select number,type,app,grp as 'group',short,body,state,source,impact,urgency,requester,created_at,updated_at from tickets where number=?", (number,))
    if not t: return None
    return {**t[0], "comments": DB.rows("select author,text,kind,ts from ticket_comments where number=? order by id", (number,)), "attachments": list_attachments(number)}

def add_comment(number, text, author="demo.user"):
    if not text.strip(): raise ValueError("comment is empty")
    if not DB.execute("select 1 from tickets where number=?", (number,)): raise KeyError(number)
    DB.execute("insert into ticket_comments(number,author,text) values(?,?,?)", (number, author, text.strip()))
    DB.execute("update tickets set updated_at=? where number=?", (stamp(), number)); DB.commit()

def set_state(number, state, by="demo.user"):
    if state not in STATES: raise ValueError("bad state")
    old = DB.execute("select state from tickets where number=?", (number,)).fetchone()
    if not old: raise KeyError(number)
    if old["state"] != state:
        DB.execute("update tickets set state=? where number=?", (state, number)); add_event(number, f"Status changed from {old['state']} to {state} by {by}", by)
    DB.commit()

def resolve(number, note, by="demo.user"):
    if len(note.strip()) < 10: raise ValueError("Please describe the fix (at least 10 characters) so it can be reused")
    DB.execute("insert into ticket_comments(number,author,text) values(?,?,?)", (number, by, "Resolution: " + note.strip())); set_state(number, "resolved", by)

def escalate(number, note, by="demo.user"):
    """L2 -> L3 hand-off: reassign to the L3 group from the rules table and require a hand-off note."""
    if len(note.strip()) < 10: raise ValueError("Add a hand-off note (what was tried, what is needed) of at least 10 characters")
    t = DB.execute("select app,state from tickets where number=?", (number,)).fetchone()
    if not t: raise KeyError(number)
    row = DB.execute("select l3 from rules where app=?", (t["app"],)).fetchone()
    if not row: raise ValueError("No L3 group is configured for this application")
    DB.execute("update tickets set grp=? where number=?", (row["l3"], number))
    DB.execute("insert into ticket_comments(number,author,text) values(?,?,?)", (number, by, "Hand-off to L3: " + note.strip()))
    add_event(number, f"Escalated to {row['l3']} by {by}", by)
    if t["state"] == "new": set_state(number, "in_progress", by)
    DB.commit(); return row["l3"]

def promote_to_kb(number, by="demo.user"):
    """Knowledge-centred service: turn a resolved ticket's fix into a knowledge article the assistant can cite."""
    t = get_ticket(number)
    if not t: raise KeyError(number)
    if t["state"] != "resolved": raise ValueError("Only resolved tickets can be turned into an article")
    fixes = [c["text"][len("Resolution: "):] for c in t["comments"] if c["text"].startswith("Resolution: ")]
    if not fixes: raise ValueError("Add a resolution note first")
    text = f"{t['short']}. Problem: {t['body'].splitlines()[0] if t['body'] else t['short']}. Fix: {' '.join(fixes)}"
    id_ = add_doc({"id": f"kb-{number}", "source": "manual", "app": t["app"], "title": f"Fix: {t['short']}", "url": f"ticket://{number}", "text": text})
    add_event(number, f"Fix published as knowledge article {id_} by {by}", by); DB.commit(); return id_

# ---- readiness and business statistics ------------------------------------------
SYMPTOM = re.compile(r"\b[45]\d\d\b|error|exception|time(?:d)? ?out|fail|blank|stuck|loop|mismatch|differ|crash|reject|pending|does not|doesn't|can't|cannot|unable|not start|wrong|incorrect", re.I)
CODE = re.compile(r"\b[45]\d\d\b")

def readiness(t, n_attachments=0):
    """Does an incident arrive with the basics an L2/L3 engineer needs? Four checks: application, environment, a specific symptom or error, and evidence or steps already tried.
    (AI-assisted tickets get these from follow-up questions, log lookup and checked documents; hand-written ones depend on the person.)"""
    body = t["body"] or ""
    problem = re.sub(r"^Problem:\s*", "", body.split("\n")[0]).strip()
    def field(name):
        m = re.search(rf"^{name}:\s*(.+)$", body, re.M | re.I); return m.group(1).strip().lower() if m else ""
    checks = {"Application": t["app"] in APPS,
              "Environment": bool(re.search(r"^Environment:\s*(prod|uat|dev)\b", body, re.I | re.M)),
              "Specific symptom or error": len(problem) >= 15 and bool(SYMPTOM.search(problem)),
              "Evidence or steps already tried": bool(n_attachments or field("Log errors") not in ("", "none found", "none") or field("Docs already checked") not in ("", "none")
                                                   or field("Already tried") or CODE.search(body))}
    return {"checks": checks, "ready": all(checks.values()), "missing": [k for k, v in checks.items() if not v]}

def business_stats():
    """Per-application ticket counts raised with the AI assistant vs without AI, and how many incidents arrive ready for L2/L3."""
    att = {r["number"]: r["n"] for r in DB.rows("select number, count(*) as n from attachments group by number")}
    per = {a: {"app": a, "total": 0, "ai": 0, "manual": 0, "open": 0, "breached": 0, "incidents": 0, "ready": 0} for a in APPS}
    ready_by = {"ai": [0, 0], "manual": [0, 0]}; missing = {"ai": {}, "manual": {}}
    for t in DB.rows("select number,type,app,body,state,source,urgency,created_at from tickets"):
        src = "ai" if t["source"] == "ai" else "manual"
        row = per.setdefault(t["app"], {"app": t["app"], "total": 0, "ai": 0, "manual": 0, "open": 0, "breached": 0, "incidents": 0, "ready": 0})
        row["total"] += 1; row[src] += 1
        if t["state"] != "resolved":
            row["open"] += 1; row["breached"] += sla(t)["state"] == "breached"
        if t["type"] == "INC":                                   # user requests (access, changes) need no diagnostics
            r = readiness(t, att.get(t["number"], 0)); row["incidents"] += 1; ready_by[src][1] += 1
            if r["ready"]: row["ready"] += 1; ready_by[src][0] += 1
            for m in r["missing"]: missing[src][m] = missing[src].get(m, 0) + 1
    rows = list(per.values()); n = lambda k: sum(r[k] for r in rows)
    return {"apps": rows, "total": n("total"), "ai": n("ai"), "manual": n("manual"), "ready_by": ready_by, "missing": missing}

# ---- attachments ------------------------------------------------------------------
def validate_upload(filename, size):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT: raise ValueError(f"'{filename}': file type {ext or '(none)'} is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    if size <= 0: raise ValueError(f"'{filename}' is empty")
    if size > MAX_FILE_BYTES: raise ValueError(f"'{filename}' is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    return True

def add_attachment(number, filename, data, mime="application/octet-stream"):
    validate_upload(filename, len(data))
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(filename))[:100]
    if DB.execute("select count(*) as n from attachments where number=?", (number,))[0]["n"] >= MAX_FILES: raise ValueError(f"At most {MAX_FILES} attachments per ticket")
    DB.execute("insert into attachments(number,filename,mime,size,data) values(?,?,?,?,?)", (number, name, mime, len(data), data))
    add_event(number, f"Attachment added: {name} ({len(data) // 1024 or 1} KB)"); DB.commit()

def list_attachments(number):
    return DB.rows("select id,filename,mime,size,ts from attachments where number=? order by id", (number,))

def get_attachment(id_):
    r = DB.rows("select filename,mime,data from attachments where id=?", (id_,)); return r[0] if r else None

# ---- knowledge docs -------------------------------------------------------------
def list_docs():
    out = DB.rows("select id,source,app,title,url,acl,text,added_at from kb_docs order by rowid")
    for d in out: d["acl"] = d["acl"].split(",")
    return out

def add_doc(d):
    """Insert a doc (dict with text; id/source/app/title/url/acl optional). Used by ingestion, the paste form, ticket promotion and the Google Doc import."""
    id_ = d.get("id") or f"doc-{uuid.uuid4().hex[:8]}"
    DB.execute("insert or replace into kb_docs(id,source,app,title,url,acl,text) values(?,?,?,?,?,?,?)",
               (id_, d.get("source", "manual"), d.get("app", "all"), d.get("title") or d["text"][:60], d.get("url", ""), ",".join(d.get("acl", ["staff"])), d["text"]))
    DB.commit(); return id_

def gdoc_export_url(url):
    m = re.match(r"https://docs\.google\.com/document/d/([\w-]+)", url.strip())
    if not m: raise ValueError("Only Google Docs links (https://docs.google.com/document/d/...) are supported")
    return f"https://docs.google.com/document/d/{m.group(1)}/export?format=txt"

def import_gdoc(url, app="all", fetch=None, acl=None):
    """Import a Google Doc shared as 'anyone with the link'. No API key needed; private docs are refused. The text is stored as untrusted content."""
    import httpx
    r = (fetch or (lambda u: httpx.get(u, follow_redirects=True, timeout=15)))(gdoc_export_url(url))
    text = r.text
    if r.status_code != 200 or "text/plain" not in r.headers.get("content-type", "text/plain") or text.lstrip().startswith("<"):
        raise ValueError("Could not read the document. Set sharing to 'Anyone with the link can view' and try again.")
    text = text.strip()[:50000]
    if not text: raise ValueError("The document is empty")
    title = text.splitlines()[0].strip()[:80]
    return add_doc({"source": "google-docs", "app": app, "title": title, "url": url, "text": text, "acl": acl or ["staff"]})
