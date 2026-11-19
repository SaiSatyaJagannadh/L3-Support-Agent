"""L3 Assist: Streamlit front end for the L3 support agent POC. Runs the agent, database and knowledge base in-process (no separate API needed).
Run locally:  streamlit run streamlit_app.py        Deploy: Streamlit Community Cloud, main file = streamlit_app.py"""
import os, sys, time, uuid, tempfile
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="L3 Assist", page_icon="🛟", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "poc"))
try:                                          # optional keys can come from Streamlit secrets (Cloud) or a .env file (local)
    for k, v in st.secrets.items():
        if isinstance(v, str): os.environ.setdefault(k, v)
except Exception: pass
def _writable(p):
    try: open(p, "a").close(); return True
    except OSError: return False
_db = os.environ.get("POC_DB") or str(ROOT / "l3.db")
os.environ["POC_DB"] = _db if _db == ":memory:" or _writable(_db) else str(Path(tempfile.gettempdir()) / "l3.db")   # Cloud filesystems may be read-only/ephemeral
import core, store                            # noqa: E402  (after env setup: db.py reads POC_DB and .env on import)
from data import APPS, ENVS, IMPACT           # noqa: E402

SRC = {"confluence": "Confluence", "sharepoint": "SharePoint", "onenote": "OneNote", "gitlab": "GitLab", "google-docs": "Google Docs", "manual": "Added manually"}
SRC_ICON = {"confluence": "📘", "sharepoint": "🗂️", "onenote": "📓", "gitlab": "🦊", "google-docs": "📄", "manual": "✍️"}
STATE = {"new": "🔵 New", "in_progress": "🟠 In progress", "resolved": "🟢 Resolved"}
ORIGIN = {"ai": "🤖 Created by AI", "manual": "✍️ Created manually", "seed": "📁 Sample ticket"}
ROLES = {"Support staff": ["staff"], "L3 engineer": ["staff", "l3"]}
SUGGEST = ["PayFlow 504 timeout on disbursement", "WealthPlan login loop after SSO", "BranchDesk attachment upload fails"]

st.markdown("""<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:2rem; max-width:1100px}
.brand {font-size:1.35rem; font-weight:700; letter-spacing:-.02em; color:#4f46e5; margin-bottom:.2rem}
.sub {color:#6b7280; font-size:.85rem; margin-bottom:1rem}
.hero {text-align:center; padding:2.2rem 0 1rem} .hero h1 {font-size:2rem; margin-bottom:.3rem} .hero p {color:#6b7280}
div[data-testid="stMetric"] {background:#f8fafc; border:1px solid #e5e7eb; border-radius:12px; padding:.8rem 1rem}
div[data-testid="stSidebar"] .stRadio label {padding:.35rem .2rem}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="brand">🛟 L3 Assist</div><div class="sub">AI-assisted L3 support</div>', unsafe_allow_html=True)
    page = st.radio("Navigate", ["💬 Assistant", "🎫 Tickets", "📚 Knowledge"], key="nav", label_visibility="collapsed")
    st.divider()
    role = st.selectbox("Viewing as", list(ROLES), help="Documents are filtered by access group. Switch to 'L3 engineer' to see the L3-only runbook.")
    groups = ROLES[role]
    if page.endswith("Assistant"):
        if st.button("➕ New chat", use_container_width=True):
            for k in ("thread", "msgs", "draft", "status"): st.session_state.pop(k, None)
            st.rerun()
    with st.expander("System status"):
        live = lambda var: "🟢 live" if os.getenv(var) else "⚪ built-in demo"
        st.markdown(f"- Answers: {live('OPENAI_API_KEY') if os.getenv('OPENAI_API_KEY') else live('AZURE_OPENAI_ENDPOINT')}\n- Search: {live('AZURE_SEARCH_ENDPOINT')}\n- Tickets: {live('SN_INSTANCE')}\n- Sign-in: {live('AAD_TENANT_ID')}\n- Database: SQLite")
        st.caption("Keys are optional. See POC-NOTES.md.")

def cites_row(cites):
    docs = {d["id"]: d for d in store.list_docs()}
    cols = st.columns(min(len(cites), 2))
    for col, c in zip(cols, cites[:2]):
        d = docs.get(c["id"])
        with col.popover(f"{SRC_ICON.get(c['source'], '📄')} {(c.get('title') or c['id'])[:48]}", use_container_width=True):
            st.markdown(f"**{c.get('title') or c['id']}**")
            st.caption(f"Source: {SRC.get(c['source'], c['source'])} · App: {d['app'] if d else '?'}")
            st.write(d["text"] if d else "")

def words(text):
    for w in text.split(" "):
        yield w + " "; time.sleep(0.012)

def rate(mid):
    v = st.session_state.get(f"fb_{mid}")
    if v is not None:
        core.DB.execute("insert into feedback values(?,?,?)", (st.session_state.get("thread", ""), 1 if v == 1 else -1, "")); core.DB.commit()
        st.toast("Thanks for the feedback")

def goto_ticket(num):
    st.session_state.nav = "🎫 Tickets"; st.session_state.sel_ticket = num

def run_turn(**inp):
    st.session_state.thread = t = st.session_state.get("thread") or str(uuid.uuid4())
    with st.spinner("Working on it…"):
        r = core.run(t, _t=t, groups=groups, **inp)
    st.session_state.status = r["status"]
    if r["status"] == "needs_approval":
        st.session_state.draft = r
        st.session_state.msgs.append({"role": "assistant", "id": uuid.uuid4().hex[:6], "text": "I've drafted a ticket from our conversation. Review it below, then submit when you're happy.", "trace": r.get("trace"), "stream": True})
    else:
        st.session_state.draft = None
        st.session_state.msgs.append({"role": "assistant", "id": uuid.uuid4().hex[:6], "text": r["reply"], "cites": r.get("citations") or [], "trace": r.get("trace") or [], "ticket": r.get("ticket"), "stream": True})

# ---------------------------------------------------------------- Assistant
def assistant():
    ss = st.session_state; ss.setdefault("msgs", []); act = None
    if not ss.msgs:
        st.markdown('<div class="hero"><h1>How can I help today?</h1><p>Describe the problem. I answer from your documents, ask follow-ups when needed, and raise a ticket only after you approve.</p></div>', unsafe_allow_html=True)
        cols = st.columns(len(SUGGEST))
        for col, s in zip(cols, SUGGEST):
            if col.button(s, use_container_width=True, key=f"sg_{s}"): act = {"message": s}
    for m in ss.msgs:
        with st.chat_message(m["role"], avatar="🧑‍💻" if m["role"] == "user" else "🛟"):
            if m.pop("stream", False) and m["role"] == "assistant": st.write_stream(words(m["text"]))
            else: st.markdown(m["text"])
            if m.get("cites"): cites_row(m["cites"])
            if m.get("ticket"):
                st.success(f"🎫 {m['ticket']}"); st.button("Open in Tickets", key=f"open_{m['id']}", on_click=goto_ticket, args=(m["ticket"],))
            if m.get("trace"):
                with st.expander("How I got this answer"):
                    st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(m["trace"], 1)))
            if m["role"] == "assistant" and m.get("cites"):
                st.feedback("thumbs", key=f"fb_{m['id']}", on_change=rate, args=(m["id"],))
    d = ss.get("draft")
    if d:
        with st.container(border=True):
            dr = d["draft"]; urg = {"all": 1, "team": 2, "me": 3}[dr["impact"]]
            st.markdown("#### 🎫 Draft ticket")
            st.text_input("Summary", dr["short"], disabled=True); st.text_area("Details", dr["body"], height=190, disabled=True)
            st.caption(f"Priority P{urg} (from the impact you gave). The assignment group is set by the routing rules after you submit. Nothing is created until you click Submit.")
            if d["similar"]:
                st.markdown("**Similar tickets** — link instead of creating a duplicate:")
                for s in d["similar"]:
                    a, b = st.columns([4, 1]); a.markdown(f"**{s['number']}** · {STATE[s['state']]} · {s['text']}" + (f"  \n_Fix:_ {s['resolution']}" if s["resolution"] else ""))
                    if b.button("Same issue", key=f"ln_{s['number']}"): act = {"resume": {"decision": "link", "inc": s["number"]}}
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Submit ticket", type="primary", key="submit"): act = {"resume": {"decision": "create"}}
            if c2.button("Cancel", key="cancel"): act = {"resume": {"decision": "cancel"}}
    elif ss.get("status") == "clarify" and ss.msgs:
        last = ss.msgs[-1]["text"].lower()
        opts = ["Just me", "My team", "Everyone"] if "affected" in last else list(ENVS) if "environment" in last else list(APPS)
        cols = st.columns(len(opts) + 2)
        for col, o in zip(cols, opts):
            if col.button(o, key=f"ch_{o}", use_container_width=True): act = {"message": o}
    if ss.get("thread") and not d and ss.get("status") in ("answered", "cancelled"):
        if st.button("🎫 Still stuck? Raise a ticket", key="stuck"): act = {"action": "not_solved"}
    prompt = st.chat_input("Describe the issue…", disabled=bool(d))
    if prompt: act = {"message": prompt}
    if act:
        if "message" in act:
            ss.msgs.append({"role": "user", "text": act["message"]}); act = {"action": "chat", **act}
        elif act.get("action") == "not_solved": ss.msgs.append({"role": "user", "text": "I'm still stuck — please raise a ticket."})
        run_turn(**act); st.rerun()

# ---------------------------------------------------------------- Tickets
@st.dialog("New ticket")
def new_ticket_dialog():
    st.caption("Create a ticket yourself, no AI involved. It is routed by the same rules table.")
    short = st.text_input("Summary *", placeholder="e.g. Receipt printer jams at branch 4")
    app = st.selectbox("Application", list(APPS), format_func=APPS.get)
    desc = st.text_area("Description", placeholder="What happened, error text, when it started")
    impact = st.radio("Who is affected?", list(IMPACT), format_func=IMPACT.get, horizontal=True, index=1)
    if st.button("Create ticket", type="primary"):
        if len(short.strip()) < 5: st.error("Please enter a summary of at least 5 characters."); return
        num, grp = store.create_ticket(app=app, short=short.strip(), body=desc.strip() or short.strip(), impact=impact, source="manual")
        st.session_state.flash = f"Created {num}, assigned to {grp}"; st.rerun()

def tickets():
    st.markdown("## Tickets")
    if "flash" in st.session_state: st.success(st.session_state.pop("flash"))
    allt = store.list_tickets()
    m = st.columns(4)
    m[0].metric("Total", len(allt)); m[1].metric("New", sum(t["state"] == "new" for t in allt))
    m[2].metric("In progress", sum(t["state"] == "in_progress" for t in allt)); m[3].metric("Resolved", sum(t["state"] == "resolved" for t in allt))
    f = st.columns([3, 2, 2, 2])
    q = f[0].text_input("Search", placeholder="Search tickets", label_visibility="collapsed")
    state = f[1].selectbox("State", ["All states", *STATE], format_func=lambda x: x if x == "All states" else STATE[x], label_visibility="collapsed")
    origin = f[2].selectbox("Origin", ["All origins", *ORIGIN], format_func=lambda x: x if x == "All origins" else ORIGIN[x], label_visibility="collapsed")
    if f[3].button("➕ New ticket", type="primary", use_container_width=True): new_ticket_dialog()
    rows = store.list_tickets(None if state.startswith("All") else state, None if origin.startswith("All") else origin, q or None)
    if not rows: st.info("No tickets match."); return
    table = [{"Ticket": r["number"], "Summary": r["short"], "App": r["app"], "Priority": f"P{r['urgency']}", "State": STATE[r["state"]], "Group": r["group"], "Origin": ORIGIN[r["source"]], "Created": r["created_at"][:16]} for r in rows]
    ev = st.dataframe(table, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key="tbl")
    sel = rows[ev.selection.rows[0]]["number"] if ev.selection.rows else st.session_state.get("sel_ticket")
    if not sel: st.caption("Select a row to see details."); return
    t = store.get_ticket(sel)
    if not t: return
    with st.container(border=True):
        st.markdown(f"### {t['number']} · {t['short']}")
        st.caption(f"{STATE[t['state']]} · {ORIGIN[t['source']]} · {APPS.get(t['app'], t['app'])} · P{t['urgency']} · {t['group']} · created {t['created_at'][:16]} by {t['requester']}")
        st.text(t["body"])
        st.markdown("**Activity**")
        for c in t["comments"]: st.markdown(f"**{c['author']}** · {c['ts'][:16]}  \n{c['text']}")
        if not t["comments"]: st.caption("No activity yet.")
        with st.form(f"cm_{sel}", clear_on_submit=True):
            txt = st.text_area("Add a comment", label_visibility="collapsed", placeholder="Add a comment")
            if st.form_submit_button("Comment") and txt.strip(): store.add_comment(sel, txt); st.rerun()
        s1, s2 = st.columns([2, 1])
        new = s1.selectbox("Status", list(STATE), index=list(STATE).index(t["state"]), format_func=STATE.get, key=f"st_{sel}")
        if new != t["state"]: store.set_state(sel, new); st.rerun()

# ---------------------------------------------------------------- Knowledge
@st.dialog("Add a document")
def add_doc_dialog():
    title = st.text_input("Title *"); app = st.selectbox("Application", ["all", *APPS], format_func=lambda a: "All applications" if a == "all" else APPS[a])
    src = st.selectbox("Source label", [s for s in SRC if s != "google-docs"], format_func=SRC.get)
    text = st.text_area("Content *", height=200)
    if st.button("Add to knowledge base", type="primary"):
        if len(title.strip()) < 3 or len(text.strip()) < 20: st.error("Add a title and at least a few sentences of content."); return
        store.add_doc({"title": title.strip(), "text": text.strip(), "app": app, "source": src}); st.session_state.flash = f"Added “{title.strip()}”"; st.rerun()

@st.dialog("Import a Google Doc")
def import_dialog():
    st.caption("Share the doc as **Anyone with the link can view**, then paste the link. No Google login or key is used; private docs are refused.")
    url = st.text_input("Google Docs link", placeholder="https://docs.google.com/document/d/…/edit")
    app = st.selectbox("Application", ["all", *APPS], format_func=lambda a: "All applications" if a == "all" else APPS[a])
    if st.button("Import", type="primary"):
        try: store.import_gdoc(url, app)
        except Exception as e: st.error(str(e)); return
        st.session_state.flash = "Imported the Google Doc"; st.rerun()

def knowledge():
    st.markdown("## Knowledge base")
    if "flash" in st.session_state: st.success(st.session_state.pop("flash"))
    docs = [d for d in store.list_docs() if set(d["acl"]) & set(groups)]
    st.caption(f"{len(docs)} documents visible to **{role}**. The assistant only answers from these, and only cites what you can see.")
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

{"💬 Assistant": assistant, "🎫 Tickets": tickets, "📚 Knowledge": knowledge}[page]()
