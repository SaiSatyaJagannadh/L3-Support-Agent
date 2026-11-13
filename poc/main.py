from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid, json, core, evals
from fastapi import Depends
from fastapi.responses import StreamingResponse
from auth import user

app = FastAPI(title="L3 Support Agent POC")
class Chat(BaseModel):
    thread: str = ""
    message: str = ""
    action: str = "chat"            # chat | not_solved
class Confirm(BaseModel):
    thread: str
    decision: str                   # create | cancel | link
    inc: str = ""

# auth.user validates Entra JWTs when AAD_TENANT_ID is set, else dev header stub
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

@app.get("/tickets")
def tickets():
    return [dict(zip(("number", "app", "group", "short", "state"), r)) for r in core.DB.execute("select number,app,grp,short,state from tickets")]

class Fb(BaseModel):
    thread: str
    rating: int                     # 1 up, -1 down
    comment: str = ""
@app.post("/feedback")
def feedback(f: Fb):
    core.DB.execute("insert into feedback values(?,?,?)", (f.thread, f.rating, f.comment)); core.DB.commit(); return {"ok": True}

@app.get("/admin/summary")
def admin(u: dict = Depends(user)):
    if "L3.Admin" not in u["roles"]: raise HTTPException(403, "L3.Admin only")
    q = lambda s: core.DB.execute(s).fetchall()
    return {"feedback": q("select rating,count(*) from feedback group by rating"), "unanswered": [r[0] for r in q("select question from unanswered")],
            "tickets": q("select count(*) from tickets")[0][0], "eval": evals.run_evals()}

@app.get("/")
def ui(): return FileResponse("static/index.html")
