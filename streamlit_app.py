"""Support Assist: Streamlit front end for the support agent POC. Runs the agent, database and knowledge base in-process (no separate API needed).
Run locally:  streamlit run streamlit_app.py        Deploy: Streamlit Community Cloud, main file = streamlit_app.py"""
import os, sys, time, uuid, tempfile
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Support Assist", page_icon="🛟", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "poc"))
try:                                          # keys come from Streamlit secrets (Cloud) or a .env file (local)
    for k, v in st.secrets.items():
        if isinstance(v, str): os.environ.setdefault(k, v)
except Exception: pass
def _writable(p):
    try: open(p, "a").close(); return True
    except OSError: return False
_db = os.environ.get("POC_DB") or str(ROOT / "l3.db")
os.environ["POC_DB"] = _db if _db == ":memory:" or _writable(_db) else str(Path(tempfile.gettempdir()) / "l3.db")   # Cloud filesystems may be read-only/ephemeral
import core, store, health                    # noqa: E402  (after env setup: db.py reads POC_DB and .env on import)
from data import APPS, ENVS, IMPACT, TYPES, USERS, SLA_HOURS   # noqa: E402

SRC = {"confluence": "Confluence", "sharepoint": "SharePoint", "onenote": "OneNote", "gitlab": "GitLab", "google-docs": "Google Docs", "manual": "Added manually"}
SRC_ICON = {"confluence": "📘", "sharepoint": "🗂️", "onenote": "📓", "gitlab": "🦊", "google-docs": "📄", "manual": "✍️"}
STATE = {"new": "🔵 New", "in_progress": "🟠 In progress", "resolved": "🟢 Resolved"}
ORIGIN = {"ai": "🤖 AI-assisted", "manual": "✍️ Manual", "seed": "📁 Sample"}
TYPE_LABEL = {k: f"{v} ({k})" for k, v in TYPES.items()}
FILE_TYPES = [e.lstrip(".") for e in sorted(store.ALLOWED_EXT)]
TEXT_EXT = (".txt", ".log", ".csv", ".json", ".md")
PAGES = ["💬 Assist", "📊 Dashboard", "🎫 Tickets", "➕ New ticket", "📚 Knowledge"]
SUGGEST = ["PayFlow 504 timeout on disbursement", "WealthPlan login loop after SSO", "BranchDesk attachment upload fails"]
ss = st.session_state

st.markdown("""<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:2rem; max-width:1150px}
.brand {font-size:1.35rem; font-weight:700; letter-spacing:-.02em; color:#4f46e5; margin-bottom:.1rem}
.sub {color:#6b7280; font-size:.85rem; margin-bottom:.8rem}
.hero {text-align:center; padding:2rem 0 1rem} .hero h1 {font-size:2rem; margin-bottom:.3rem} .hero p {color:#6b7280}
div[data-testid="stMetric"] {background:#f8fafc; border:1px solid #e5e7eb; border-radius:12px; padding:.8rem 1rem}
.usr {display:flex; gap:.7rem; align-items:center; padding:.6rem .7rem; background:#fff; border:1px solid #e5e7eb; border-radius:12px; margin-bottom:.5rem}
.av {width:38px; height:38px; border-radius:50%; background:#4f46e5; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.9rem}
.usr b {font-size:.92rem} .usr span {color:#6b7280; font-size:.78rem}
.ok {color:#047857; font-weight:600; font-size:.85rem; margin:.3rem 0}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- user, sidebar
ss.setdefault("user_idx", 0)
user = USERS[ss.user_idx]; groups = user["groups"]
def _pick(): ss.user_idx = [u["name"] for u in USERS].index(ss.user_pick)

with st.sidebar:
    st.markdown('<div class="brand">🛟 Support Assist</div><div class="sub">AI-assisted support desk</div>', unsafe_allow_html=True)
    page = st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    ini = "".join(w[0] for w in user["name"].split())
    st.markdown(f'<div class="usr"><div class="av">{ini}</div><div><b>{user["name"]}</b><br><span>{user["role"]} · {user["team"]}</span></div></div>', unsafe_allow_html=True)
    with st.popover("Switch user", use_container_width=True):
        st.caption("Demo profiles. Each sees only the documents their access group allows.")
        st.radio("User", [u["name"] for u in USERS], index=ss.user_idx, key="user_pick", on_change=_pick, format_func=lambda n: f"{n} · {next(u['role'] for u in USERS if u['name'] == n)}")
    if page.endswith("Assist") and st.button("➕ New chat", use_container_width=True):
        for k in ("thread", "msgs", "draft", "status", "files", "show_upload"): ss.pop(k, None)
        st.rerun()
    rows = health.checks()
    st.markdown(f'<div class="ok">{"🟢 All systems online" if health.overall(rows) == "online" else "🔴 A component is down"}</div>', unsafe_allow_html=True)
    with st.expander("System status"):
        dot = {"online": "🟢", "built-in": "🔵", "down": "🔴"}
        for r in rows:
            st.markdown(f"{dot[r['status']]} **{r['name']}**  \n<span style='color:#374151;font-size:.82rem'>{r['type']}</span><br><span style='color:#6b7280;font-size:.74rem'>{r['detail']}</span>", unsafe_allow_html=True)
        st.caption("🟢 connected · 🔵 built-in demo mode (no key needed) · 🔴 down")
        if st.button("Test AI connection", key="ping"):
            ok, msg = health.ping_llm(); (st.success if ok else st.warning)(msg)

# ---------------------------------------------------------------- helpers
def cites_row(cites):
    docs = {d["id"]: d for d in store.list_docs()}
    cols = st.columns(min(len(cites), 2))
    for col, c in zip(cols, cites[:2]):
        d = docs.get(c["id"])
        with col.popover(f"{SRC_ICON.get(c['source'], '📄')} {(c.get('title') or c['id'])[:48]}", use_container_width=True):
            st.markdown(f"**{c.get('title') or c['id']}**"); st.caption(f"Source: {SRC.get(c['source'], c['source'])} · App: {d['app'] if d else '?'}"); st.write(d["text"] if d else "")

def words(text):
    for w in text.split(" "):
        yield w + " "; time.sleep(0.012)

def rate(mid):
    v = ss.get(f"fb_{mid}")
    if v is not None:
        core.DB.execute("insert into feedback values(?,?,?)", (ss.get("thread", ""), 1 if v == 1 else -1, "")); core.DB.commit(); st.toast("Thanks for the feedback")

def goto_ticket(num): ss.nav = "🎫 Tickets"; ss.sel_ticket = num
def goto(page_name): ss.nav = page_name

def read_files(uploaded):
    """UploadedFile list -> [(name, bytes, excerpt)], skipping (and reporting) files that fail validation."""
    out = []
    for f in uploaded or []:
        data = f.getvalue()
        try: store.validate_upload(f.name, len(data))
        except ValueError as e: st.error(str(e)); continue
        out.append((f.name, data, data[:1500].decode("utf-8", "ignore").strip() if f.name.lower().endswith(TEXT_EXT) else ""))
    return out

def keep_files(files):
    have = {n for n, _ in ss.setdefault("files", [])}
    for n, b, _ in files:
        if n not in have and len(ss.files) < store.MAX_FILES: ss.files.append((n, b))

def run_turn(**inp):
    ss.thread = t = ss.get("thread") or str(uuid.uuid4())
    with st.spinner("Working on it…"):
        r = core.run(t, _t=t, groups=groups, user=user["name"], **inp)
    ss.status = r["status"]
    if r["status"] == "needs_approval":
        ss.draft = r
        ss.msgs.append({"role": "assistant", "id": uuid.uuid4().hex[:6], "text": "I've drafted a ticket from our conversation. Review it below, add attachments if you like, then submit.", "trace": r.get("trace"), "stream": True})
    else:
        ss.draft = None
        ss.msgs.append({"role": "assistant", "id": uuid.uuid4().hex[:6], "text": r["reply"], "cites": r.get("citations") or [], "trace": r.get("trace") or [], "ticket": r.get("ticket"), "stream": True,
                        "no_answer": r["status"] == "answered" and not r.get("citations")})
    return r

# ---------------------------------------------------------------- Assist
def assist():
    act = None; ss.setdefault("msgs", [])
    if not ss.msgs:
        st.markdown(f'<div class="hero"><h1>Hi {user["name"].split()[0]}, how can I help?</h1><p>I check your documents first, ask follow-up questions when needed, and raise a ticket only after you approve. You can attach logs or screenshots.</p></div>', unsafe_allow_html=True)
        cols = st.columns(len(SUGGEST))
        for col, s in zip(cols, SUGGEST):
            if col.button(s, use_container_width=True, key=f"sg_{s}"): act = {"message": s}
    for m in ss.msgs:
        with st.chat_message(m["role"], avatar="🧑‍💻" if m["role"] == "user" else "🛟"):
            if m.pop("stream", False) and m["role"] == "assistant": st.write_stream(words(m["text"]))
            else: st.markdown(m["text"])
            if m.get("attached"): st.caption("📎 " + ", ".join(m["attached"]))
            if m.get("cites"): cites_row(m["cites"])
            if m.get("ticket"):
                st.success(m["ticket"]); st.button("Open ticket", key=f"open_{m['id']}", on_click=goto_ticket, args=(m["ticket"],))
            if m.get("trace"):
                with st.expander("How I got this answer"): st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(m["trace"], 1)))
            if m["role"] == "assistant" and m.get("cites"): st.feedback("thumbs", key=f"fb_{m['id']}", on_change=rate, args=(m["id"],))
    d = ss.get("draft")
    last = ss.msgs[-1] if ss.msgs else {}
    if d:
        dr = d["draft"]; urg = {"all": 1, "team": 2, "me": 3}[dr["impact"]]
        with st.container(border=True):
            st.markdown("#### 🎫 Draft ticket")
            c1, c2 = st.columns([3, 2])
            c1.text_input("Short description", dr["short"], disabled=True)
            ttype = c2.selectbox("Type", list(TYPES), format_func=TYPE_LABEL.get, key="dtype")
            st.text_area("Description", dr["body"], height=190, disabled=True)
            st.caption(f"Caller: {user['name']} · Priority P{urg} (from the impact you gave, target {SLA_HOURS[urg]}h) · the assignment group is set by the routing rules after you submit.")
            ups = st.file_uploader("Attachments (logs, screenshots; max 5 files, 5 MB each)", accept_multiple_files=True, type=FILE_TYPES, key="draft_up")
            if ss.get("files"): st.caption("Already attached from chat: " + ", ".join(n for n, _ in ss.files))
            if d["similar"]:
                st.markdown("**Similar tickets**, link instead of creating a duplicate:")
                for s in d["similar"]:
                    a, b = st.columns([4, 1]); a.markdown(f"**{s['number']}** · {STATE[s['state']]} · {s['text']}" + (f"  \n_Fix:_ {s['resolution']}" if s["resolution"] else ""))
                    if b.button("Same issue", key=f"ln_{s['number']}"): act = {"resume": {"decision": "link", "inc": s["number"]}}
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Submit ticket", type="primary", key="submit"):
                fl = read_files(ups)
                if len(fl) == len(ups or []):
                    keep_files(fl); act = {"resume": {"decision": "create", "type": ttype}}
            if c2.button("Cancel", key="cancel"): act = {"resume": {"decision": "cancel"}}
    elif ss.get("status") == "clarify" and ss.msgs:
        lt = last.get("text", "").lower()
        opts = ["Just me", "My team", "Everyone"] if "affected" in lt else list(ENVS) if "environment" in lt else list(APPS)
        cols = st.columns(len(opts) + 2)
        for col, o in zip(cols, opts):
            if col.button(o, key=f"ch_{o}", use_container_width=True): act = {"message": o}
    elif last.get("no_answer"):                       # nothing in the documents: offer attach-more-detail or a ticket
        st.info("I found nothing in the documents for this. Would you like to give me more detail, or hand it to the team?")
        c1, c2, _ = st.columns([2, 2, 2])
        if c1.button("📎 Attach a log or screenshot", key="want_attach", use_container_width=True): ss.show_upload = True
        if c2.button("🎫 Create a ticket from this", key="stuck_na", use_container_width=True): act = {"action": "not_solved"}
        if ss.get("show_upload"):
            ups = st.file_uploader("Attach files (text logs are read; images and PDFs go on the ticket)", accept_multiple_files=True, type=FILE_TYPES, key="assist_up")
            if ups and st.button("Search again with these files", key="use_files", type="primary"):
                fl = read_files(ups); keep_files(fl)
                q = next((m["text"] for m in reversed(ss.msgs) if m["role"] == "user" and not m.get("attached")), "")
                ex = " ".join(e for _, _, e in fl if e)
                ss.msgs.append({"role": "user", "text": "Here are the files.", "attached": [n for n, _, _ in fl]}); ss.show_upload = False
                act = {"action": "chat", "message": f"{q} {ex}".strip()}
    if ss.get("thread") and not d and ss.get("status") in ("answered", "cancelled") and not last.get("no_answer"):
        if st.button("🎫 Still stuck? Raise a ticket", key="stuck"): act = {"action": "not_solved"}
    prompt = st.chat_input("Describe the issue, or attach a log…", accept_file="multiple", file_type=FILE_TYPES, disabled=bool(d))
    if prompt:
        text, files = (prompt, []) if isinstance(prompt, str) else (prompt.get("text") or "", list(prompt.get("files") or []))
        fl = read_files(files); keep_files(fl)
        if text.strip() or fl:
            ss.msgs.append({"role": "user", "text": text or "(attachment)", "attached": [n for n, _, _ in fl]})
            act = {"action": "chat", "message": (text + " " + " ".join(e for _, _, e in fl if e)).strip() or "attachment"}
    if act:
        if "message" in act and "action" not in act:
            ss.msgs.append({"role": "user", "text": act["message"]}); act = {"action": "chat", **act}
        elif act.get("action") == "not_solved": ss.msgs.append({"role": "user", "text": "I'm still stuck, please raise a ticket."})
        r = run_turn(**act)
        if r["status"] == "ticket" and ss.get("files"):        # attach what was shared in chat to the ticket the AI just created
            failed = []
            for n, b in ss.files:
                try: store.add_attachment(r["ticket"], n, b)
                except ValueError as e: failed.append(str(e))
            ss.msgs[-1]["attached"] = [n for n, _ in ss.files]; ss.files = []
            if failed: ss.msgs[-1]["text"] += " (Some attachments were not added: " + "; ".join(failed) + ")"
        st.rerun()

# ---------------------------------------------------------------- Dashboard
def dashboard():
    import pandas as pd
    st.markdown("## Dashboard"); st.caption(f"Welcome back, {user['name'].split()[0]}. Priorities and SLA targets: P1 {SLA_HOURS[1]}h · P2 {SLA_HOURS[2]}h · P3 {SLA_HOURS[3]}h.")
    allt = store.list_tickets(); op = [t for t in allt if t["state"] != "resolved"]
    for t in allt: t["sla"] = store.sla(t)
    risk = [t for t in op if t["sla"]["state"] == "at risk"]; br = [t for t in op if t["sla"]["state"] == "breached"]
    answered = core.DB.execute("select count(*) as n from conversations where outcome='answered'")[0]["n"]
    m = st.columns(5)
    m[0].metric("Open tickets", len(op)); m[1].metric("P1 open", sum(t["urgency"] == 1 for t in op)); m[2].metric("SLA at risk", len(risk)); m[3].metric("SLA breached", len(br)); m[4].metric("Answered by assistant", answered, help="Chats resolved from documents without a ticket")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Open tickets by priority**"); st.bar_chart(pd.DataFrame({"tickets": [sum(t["urgency"] == p for t in op) for p in (1, 2, 3)]}, index=["P1", "P2", "P3"]))
    with c2:
        st.markdown("**Tickets by state**"); st.bar_chart(pd.DataFrame({"tickets": [sum(t["state"] == s for t in allt) for s in STATE]}, index=[STATE[s][2:] for s in STATE]))
    st.markdown("### SLA watchlist")
    wl = sorted(br + risk, key=lambda t: t["sla"]["hours_left"])
    if wl: st.dataframe([{"Ticket": t["number"], "Summary": t["short"], "Priority": f"P{t['urgency']}", "Group": t["group"], "SLA": t["sla"]["label"]} for t in wl], hide_index=True, use_container_width=True)
    else: st.success("No tickets at risk.")
    st.markdown("### Reported by me")
    mine = [t for t in allt if t["requester"] == user["name"]]
    if mine: st.dataframe([{"Ticket": t["number"], "Summary": t["short"], "State": STATE[t["state"]], "SLA": t["sla"]["label"]} for t in mine], hide_index=True, use_container_width=True)
    else: st.caption("You have not reported any tickets yet.")
    st.button("➕ New ticket", type="primary", on_click=goto, args=("➕ New ticket",))

# ---------------------------------------------------------------- New ticket (separate page)
def new_ticket():
    st.markdown("## New ticket"); st.caption("Create a ticket yourself, no AI involved. It is routed by the same rules table as AI-assisted tickets.")
    if ss.get("created"):
        num, grp, nf = ss.pop("created"); st.success(f"Created **{num}**, assigned to **{grp}**" + (f" with {nf} attachment(s)" if nf else ""))
        st.button(f"Open {num}", on_click=goto_ticket, args=(num,))
    with st.form("new_ticket", clear_on_submit=True):
        c = st.columns([2, 2, 2])
        ttype = c[0].radio("Ticket type", list(TYPES), format_func=TYPE_LABEL.get, horizontal=True, help="Incident = something is broken. User request = access, change or information.")
        app = c[1].selectbox("Application", list(APPS), format_func=APPS.get)
        env = c[2].selectbox("Environment", [*ENVS, "n/a"])
        short = st.text_input("Short description *", placeholder="e.g. Receipt printer jams at branch 4", max_chars=120)
        desc = st.text_area("Description", placeholder="What happened, exact error text, when it started, what you already tried", height=140)
        impact = st.radio("Who is affected?", list(IMPACT), format_func=IMPACT.get, horizontal=True, index=1, help="Sets the priority: everyone P1, team P2, just me P3")
        ups = st.file_uploader("Attachments (logs, screenshots, documents; max 5 files, 5 MB each)", accept_multiple_files=True, type=FILE_TYPES)
        st.caption(f"Caller: {user['name']} · The number is assigned on creation: INC + 7 digits for incidents, UR + 8 digits for user requests (always 10 characters).")
        if st.form_submit_button("Create ticket", type="primary"):
            if len(short.strip()) < 5: st.error("Please enter a short description of at least 5 characters.")
            else:
                fl = read_files(ups)
                if len(fl) == len(ups or []):
                    try:
                        num, grp = store.create_ticket(app=app, short=short.strip(), body=f"{desc.strip() or short.strip()}\n\nApplication: {APPS[app]}\nEnvironment: {env}",
                                                       impact=impact, source="manual", type=ttype, requester=user["name"], attachments=[(n, b) for n, b, _ in fl])
                        ss.created = (num, grp, len(fl)); st.rerun()
                    except ValueError as e: st.error(str(e))

# ---------------------------------------------------------------- Tickets
def tickets():
    top = st.columns([4, 1]); top[0].markdown("## Tickets"); top[1].button("➕ New ticket", type="primary", use_container_width=True, on_click=goto, args=("➕ New ticket",))
    f = st.columns([3, 2, 2, 2, 2])
    q = f[0].text_input("Search", placeholder="Search number or text", label_visibility="collapsed")
    ttype = f[1].selectbox("Type", ["All types", *TYPES], format_func=lambda x: x if x.startswith("All") else TYPE_LABEL[x], label_visibility="collapsed")
    state = f[2].selectbox("State", ["All states", *STATE], format_func=lambda x: x if x.startswith("All") else STATE[x], label_visibility="collapsed")
    origin = f[3].selectbox("Origin", ["All origins", *ORIGIN], format_func=lambda x: x if x.startswith("All") else ORIGIN[x], label_visibility="collapsed")
    mine = f[4].toggle("Reported by me")
    rows = store.list_tickets(None if state.startswith("All") else state, None if origin.startswith("All") else origin, q or None, user["name"] if mine else None, None if ttype.startswith("All") else ttype)
    if "flash" in ss: st.success(ss.pop("flash"))
    if not rows: st.info("No tickets match."); return
    table = [{"Number": r["number"], "Type": r["type"], "Short description": r["short"], "Caller": r["requester"], "Priority": f"P{r['urgency']}", "State": STATE[r["state"]], "Assignment group": r["group"],
              "SLA": store.sla(r)["label"], "Origin": ORIGIN[r["source"]], "Created (UTC)": r["created_at"][:16]} for r in rows]
    ev = st.dataframe(table, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key="tbl")
    sel = rows[ev.selection.rows[0]]["number"] if ev.selection.rows else ss.get("sel_ticket")
    if not sel: st.caption("Select a row to open the ticket."); return
    t = store.get_ticket(sel)
    if not t: return
    with st.container(border=True):
        sl = store.sla(t)
        st.markdown(f"### {t['number']} · {t['short']}")
        st.caption(f"{TYPES[t['type']]} · {STATE[t['state']]} · P{t['urgency']} · {sl['label']} · {t['group']} · caller {t['requester']} · {ORIGIN[t['source']]} · created {t['created_at'][:16]} UTC")
        tab = st.tabs(["Details", "Activity", f"Attachments ({len(t['attachments'])})", "Related"])
        with tab[0]:
            st.text(t["body"])
            with st.expander("Update status", expanded=False):
                new = st.selectbox("Status", list(STATE), index=list(STATE).index(t["state"]), format_func=STATE.get, key=f"st_{sel}")
                if new == "resolved" and t["state"] != "resolved":
                    note = st.text_area("Resolution note (the fix, so it can be reused)", key=f"rn_{sel}")
                    if st.button("Resolve ticket", type="primary", key=f"rs_{sel}"):
                        try: store.resolve(sel, note, user["name"]); ss.flash = f"{sel} resolved"; st.rerun()
                        except ValueError as e: st.error(str(e))
                elif new != t["state"]: store.set_state(sel, new, user["name"]); st.rerun()
            if t["state"] != "resolved" and not t["group"].startswith("L3"):
                with st.expander("Escalate to L3"):
                    note = st.text_area("Hand-off note: what was tried and what is needed", key=f"en_{sel}")
                    if st.button("Escalate to L3 team", key=f"es_{sel}"):
                        try: g = store.escalate(sel, note, user["name"]); ss.flash = f"{sel} escalated to {g}"; st.rerun()
                        except ValueError as e: st.error(str(e))
            if t["state"] == "resolved" and not any(d["id"] == f"kb-{sel}" for d in store.list_docs()):
                if st.button("📚 Publish the fix to the knowledge base", key=f"pk_{sel}"):
                    try: store.promote_to_kb(sel, user["name"]); ss.flash = "Published. The assistant can now cite this fix."; st.rerun()
                    except ValueError as e: st.error(str(e))
        with tab[1]:
            for c in t["comments"]:
                if c["kind"] == "event": st.caption(f"⚙️ {c['ts'][:16]} · {c['text']}")
                else: st.markdown(f"**{c['author']}** · {c['ts'][:16]}  \n{c['text']}")
            with st.form(f"cm_{sel}", clear_on_submit=True):
                txt = st.text_area("Add a comment", label_visibility="collapsed", placeholder="Add a comment")
                if st.form_submit_button("Comment") and txt.strip(): store.add_comment(sel, txt, user["name"]); st.rerun()
        with tab[2]:
            for a in t["attachments"]:
                x, y = st.columns([4, 1]); x.markdown(f"📎 **{a['filename']}** · {max(a['size'] // 1024, 1)} KB · {a['ts'][:16]}")
                full = store.get_attachment(a["id"]); y.download_button("Download", full["data"], file_name=full["filename"], mime=full["mime"], key=f"dl_{a['id']}")
            if not t["attachments"]: st.caption("No attachments.")
            ups = st.file_uploader("Add attachments", accept_multiple_files=True, type=FILE_TYPES, key=f"au_{sel}")
            if ups and st.button("Upload", key=f"up_{sel}"):
                ok = True
                for n, b, _ in read_files(ups):
                    try: store.add_attachment(sel, n, b)
                    except ValueError as e: st.error(str(e)); ok = False
                if ok: st.rerun()
        with tab[3]:
            hits = core.search(f"{t['short']} {t['body']}", groups, t["app"] if t["app"] in APPS else None)
            st.markdown("**Related knowledge**")
            for _, d in hits: st.markdown(f"- {SRC_ICON.get(d['source'], '📄')} **{d['title']}** ({SRC.get(d['source'], d['source'])})  \n  {core.best_sentences(t['short'] + ' ' + t['body'], d['text'])}")
            if not hits: st.caption("Nothing related in the knowledge base. Resolving this ticket and publishing the fix would fill the gap.")
            sim = [s for s in core.similar(t["app"], f"{t['short']} {t['body']}") if s["number"] != sel]
            st.markdown("**Similar tickets**")
            for s in sim: st.markdown(f"- **{s['number']}** · {STATE[s['state']]} · {s['text']}" + (f"  \n  _Fix:_ {s['resolution']}" if s["resolution"] else ""))
            if not sim: st.caption("No similar tickets.")

# ---------------------------------------------------------------- Knowledge
@st.dialog("Add a document")
def add_doc_dialog():
    title = st.text_input("Title *"); app = st.selectbox("Application", ["all", *APPS], format_func=lambda a: "All applications" if a == "all" else APPS[a])
    src = st.selectbox("Source label", [s for s in SRC if s != "google-docs"], format_func=SRC.get)
    text = st.text_area("Content *", height=200)
    if st.button("Add to knowledge base", type="primary"):
        if len(title.strip()) < 3 or len(text.strip()) < 20: st.error("Add a title and at least a few sentences of content."); return
        store.add_doc({"title": title.strip(), "text": text.strip(), "app": app, "source": src}); ss.flash = f"Added “{title.strip()}”"; st.rerun()

@st.dialog("Import a Google Doc")
def import_dialog():
    st.caption("Share the doc as **Anyone with the link can view**, then paste the link. No Google login or key is used; private docs are refused.")
    url = st.text_input("Google Docs link", placeholder="https://docs.google.com/document/d/…/edit")
    app = st.selectbox("Application", ["all", *APPS], format_func=lambda a: "All applications" if a == "all" else APPS[a])
    if st.button("Import", type="primary"):
        try: store.import_gdoc(url, app)
        except Exception as e: st.error(str(e)); return
        ss.flash = "Imported the Google Doc"; st.rerun()

def knowledge():
    st.markdown("## Knowledge base")
    if "flash" in ss: st.success(ss.pop("flash"))
    docs = [d for d in store.list_docs() if set(d["acl"]) & set(groups)]
    st.caption(f"{len(docs)} documents visible to **{user['name']}** ({user['role']}). The assistant only answers from these, and only cites what you can see.")
    f = st.columns([3, 2, 2, 2])
    q = f[0].text_input("Search", placeholder="Search documents", label_visibility="collapsed")
    src = f[1].selectbox("Source", ["All sources", *SRC], format_func=lambda x: x if x.startswith("All") else SRC[x], label_visibility="collapsed")
    if f[2].button("➕ Add document", use_container_width=True): add_doc_dialog()
    if f[3].button("📄 Import Google Doc", use_container_width=True): import_dialog()
    docs = [d for d in docs if (src.startswith("All") or d["source"] == src) and (not q or q.lower() in (d["title"] + d["text"]).lower())]
    if not docs: st.info("No documents match."); return
    table = [{"Title": d["title"], "Source": f"{SRC_ICON.get(d['source'], '📄')} {SRC.get(d['source'], d['source'])}", "App": d["app"], "Access": ", ".join(d["acl"]), "Added": d["added_at"][:10]} for d in docs]
    ev = st.dataframe(table, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key="kbtbl")
    if ev.selection.rows:
        d = docs[ev.selection.rows[0]]
        with st.container(border=True):
            st.markdown(f"### {d['title']}"); st.caption(f"{SRC.get(d['source'], d['source'])} · app: {d['app']} · access: {', '.join(d['acl'])}"); st.write(d["text"])
    else: st.caption("Select a row to read the document.")

{"💬 Assist": assist, "📊 Dashboard": dashboard, "🎫 Tickets": tickets, "➕ New ticket": new_ticket, "📚 Knowledge": knowledge}[page]()
