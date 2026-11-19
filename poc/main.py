"""Optional REST API over the same agent and store the Streamlit app uses (handy for tests, load tests and other front ends)."""
import uuid, json, core, store, evals
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from auth import user
from data import APPS, IMPACT

app = FastAPI(title="L3 Support Agent API")

class Chat(BaseModel):
    thread: str = ""
    message: str = ""
    action: str = "chat"            # chat | not_solved
class Confirm(BaseModel):
    thread: str
    decision: str                   # create | cancel | link
    inc: str = ""

# auth.user validates Entra JWTs when AAD_TENANT_ID is set, else a dev header stub
@app.post("/chat")
def chat(c: Chat, u: dict = Depends(user)):
    t = c.thread or str(uuid.uuid4())
    inp = {"_t": t, "action": c.action, "message": c.message, "groups": u["groups"]}
    if c.action == "not_solved": inp.pop("message")
    return {"thread": t, **core.run(t, **inp)}

@app.post("/chat/stream")   # SSE: same turn, answer streamed word by word
def chat_stream(c: Chat, u: dict = Depends(user)):
    r = chat(c, u)
    def gen():
        yield f"event: meta\ndata: {json.dumps({k: v for k, v in r.items() if k != 'reply'})}\n\n"
        for w in (r.get("reply") or "").split(" "): yield f"event: token\ndata: {json.dumps(w + ' ')}\n\n"
        yield "event: done\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/confirm")
def confirm(c: Confirm):
    return {"thread": c.thread, **core.run(c.thread, resume={"decision": c.decision, "inc": c.inc})}

# ---- tickets (AI-created and manual live in the same table) ----
class NewTicket(BaseModel):
    short: str = Field(min_length=5, max_length=120)
    description: str = ""
    app: str
    impact: str = "team"
@app.get("/tickets")
def tickets(state: str = "", source: str = "", q: str = ""):
    return store.list_tickets(state or None, source or None, q or None)
@app.post("/tickets", status_code=201)
def new_ticket(t: NewTicket):
    if t.app not in APPS: raise HTTPException(422, f"app must be one of {list(APPS)}")
    if t.impact not in IMPACT: raise HTTPException(422, f"impact must be one of {list(IMPACT)}")
    num, grp = store.create_ticket(app=t.app, short=t.short, body=t.description or t.short, impact=t.impact, source="manual")
    return {"number": num, "group": grp}
@app.get("/tickets/{number}")
def ticket(number: str):
    t = store.get_ticket(number)
    if not t: raise HTTPException(404, "no such ticket")
    return t
class Comment(BaseModel):
    text: str
@app.post("/tickets/{number}/comments", status_code=201)
def comment(number: str, c: Comment):
    try: store.add_comment(number, c.text)
    except KeyError: raise HTTPException(404, "no such ticket")
    except ValueError as e: raise HTTPException(422, str(e))
    return {"ok": True}

# ---- knowledge docs ----
class Doc(BaseModel):
    title: str = Field(min_length=3)
    text: str = Field(min_length=20)
    source: str = "manual"
    app: str = "all"
class Imp(BaseModel):
    url: str
    app: str = "all"
@app.get("/kb")
def kb():
    return [{**{k: v for k, v in d.items() if k != "text"}, "snippet": d["text"][:160]} for d in store.list_docs()]
@app.post("/kb", status_code=201)
def kb_add(d: Doc): return {"id": store.add_doc(d.model_dump())}
@app.post("/kb/import", status_code=201)
def kb_import(i: Imp):
    try: return {"id": store.import_gdoc(i.url, i.app)}
    except ValueError as e: raise HTTPException(422, str(e))

class Fb(BaseModel):
    thread: str
    rating: int                     # 1 up, -1 down
    comment: str = ""
@app.post("/feedback")
def feedback(f: Fb):
    core.DB.execute("insert into feedback values(?,?,?)", (f.thread, f.rating, f.comment)); core.DB.commit(); return {"ok": True}

@app.get("/admin/summary")        # API-only (not shown in the UI): L3.Admin role from the Entra token
def admin(u: dict = Depends(user)):
    if "L3.Admin" not in u["roles"]: raise HTTPException(403, "L3.Admin only")
    q = lambda s: core.DB.execute(s).fetchall()
    return {"feedback": [list(r) for r in q("select rating,count(*) from feedback group by rating")], "unanswered": [r[0] for r in q("select question from unanswered")],
            "tickets": q("select count(*) from tickets")[0][0], "eval": evals.run_evals()}
