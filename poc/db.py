"""SQLite database (stand-in for Azure SQL): schema, seed data and a small thread-safe wrapper.
File location: POC_DB env var (default l3.db in the working directory; ':memory:' for tests). Delete the file to reset the demo."""
import os, pathlib, sqlite3, threading, datetime as dt
from data import RULES, LOGS, KB, SEED_TICKETS

def _loadenv():   # tiny .env loader (no dependency); real environment variables win
    for p in (pathlib.Path.cwd() / ".env", pathlib.Path(__file__).parent.parent / ".env", pathlib.Path(__file__).parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1); v = v.strip().strip('"').strip("'")
                    if v: os.environ.setdefault(k.strip(), v)
_loadenv()

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(thread TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, app TEXT, env TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, thread TEXT, role TEXT, content TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS kb_docs(id TEXT PRIMARY KEY, source TEXT, app TEXT, title TEXT, url TEXT, acl TEXT, text TEXT, added_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tickets(number TEXT PRIMARY KEY, idem TEXT UNIQUE, app TEXT, grp TEXT, short TEXT, body TEXT, state TEXT DEFAULT 'new',
  source TEXT, impact TEXT, urgency INTEGER, thread TEXT, requester TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ticket_comments(id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, author TEXT, text TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS rules(app TEXT, category TEXT, l2 TEXT, l3 TEXT);
CREATE TABLE IF NOT EXISTS logs(app TEXT, env TEXT, level TEXT, msg TEXT);
CREATE TABLE IF NOT EXISTS feedback(thread TEXT, rating INTEGER, comment TEXT);
CREATE TABLE IF NOT EXISTS unanswered(thread TEXT, question TEXT);
CREATE TABLE IF NOT EXISTS audit(ts TEXT DEFAULT CURRENT_TIMESTAMP, thread TEXT, event TEXT, detail TEXT);
"""

class _R(list):
    fetchall = lambda s: list(s)
    fetchone = lambda s: s[0] if s else None

class _DB:
    def __init__(s, path):
        s.c = sqlite3.connect(path, check_same_thread=False); s.c.row_factory = sqlite3.Row; s.l = threading.RLock()
    def execute(s, sql, args=()):
        with s.l: return _R(s.c.execute(sql, args).fetchall())
    def rows(s, sql, args=()):   # list of dicts
        return [dict(r) for r in s.execute(sql, args)]
    def executemany(s, sql, seq):
        with s.l: return s.c.executemany(sql, seq)
    def executescript(s, sql):
        with s.l: return s.c.executescript(sql)
    def commit(s):
        with s.l: s.c.commit()

DB = _DB(os.getenv("POC_DB", "l3.db"))
DB.executescript(SCHEMA)

def seed():
    if not DB.execute("select 1 from rules"):
        DB.executemany("insert into rules values(?,?,?,?)", [(a, c, l2, l3) for a, c, l2, l3 in RULES])
    if not DB.execute("select 1 from logs"):
        DB.executemany("insert into logs values(?,?,?,?)", [(l["app"], l["env"], l["level"], l["msg"]) for l in LOGS])
    if not DB.execute("select 1 from kb_docs"):
        DB.executemany("insert into kb_docs(id,source,app,title,url,acl,text) values(?,?,?,?,?,?,?)",
                       [(d["id"], d["source"], d["app"], d["title"], d["url"], ",".join(d["acl"]), d["text"]) for d in KB])
    if not DB.execute("select 1 from tickets"):
        grp = {a: l2 for a, _, l2, _ in RULES}; now = dt.datetime.now()
        urg = {"all": 1, "team": 2, "me": 3}
        for n, app, state, imp, days, short, body, res in SEED_TICKETS:
            DB.execute("insert into tickets(number,idem,app,grp,short,body,state,source,impact,urgency,requester,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (n, n, app, grp[app], short, body, state, "seed", imp, urg[imp], "demo.user", (now - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")))
            if res: DB.execute("insert into ticket_comments(number,author,text) values(?,?,?)", (n, "L2 engineer", "Resolution: " + res))
    DB.commit()
seed()
