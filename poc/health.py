"""System status: what each part of the app is running on, with a real ping for the database and an on-demand ping for the AI connection."""
import os, time
from db import DB

def checks():
    """One row per component: name, type (what it runs on), status ('online' = in use, 'built-in' = demo fallback in use, 'down'), detail."""
    rows = []
    try:
        t0 = time.perf_counter(); DB.execute("select 1"); ms = (time.perf_counter() - t0) * 1000
        n = lambda tbl: DB.execute(f"select count(*) as n from {tbl}")[0]["n"]
        loc = os.getenv("POC_DB", "l3.db"); rows.append({"name": "Database", "type": "SQLite" + (" (in memory)" if loc == ":memory:" else " file"), "status": "online",
                     "detail": f"{n('tickets')} tickets · {n('kb_docs')} documents · {n('conversations')} conversations · ping {ms:.1f} ms"})
    except Exception as e:
        rows.append({"name": "Database", "type": "SQLite", "status": "down", "detail": str(e)})
    if os.getenv("OPENAI_API_KEY") and not (os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY")):
        rows.append({"name": "AI answers", "type": f"OpenAI · {os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}", "status": "online", "detail": "key configured; answers are written by the model from retrieved documents only"})
    elif os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY"):
        rows.append({"name": "AI answers", "type": f"Azure OpenAI · {os.getenv('AZURE_OPENAI_DEPLOYMENT', '?')}", "status": "online", "detail": "key configured"})
    else:
        rows.append({"name": "AI answers", "type": "Built-in extractive", "status": "built-in", "detail": "no AI key: quotes the best-matching sentences of the cited document"})
    rows.append({"name": "Search", "type": "Azure AI Search" if os.getenv("AZURE_SEARCH_ENDPOINT") else "Built-in keyword search", "status": "online" if os.getenv("AZURE_SEARCH_ENDPOINT") else "built-in",
                 "detail": "access-filtered; needs at least two matching key terms"})
    rows.append({"name": "Ticketing", "type": f"ServiceNow · {os.getenv('SN_INSTANCE')}" if os.getenv("SN_INSTANCE") else "Local ticket store", "status": "online" if os.getenv("SN_INSTANCE") else "built-in",
                 "detail": "INC / UR numbers, SLA, attachments, routing rules"})
    rows.append({"name": "Safety checks", "type": "Azure Prompt Shields + built-in" if os.getenv("CONTENT_SAFETY_ENDPOINT") else "Built-in", "status": "online",
                 "detail": "prompt-injection and personal-data checks on every message"})
    rows.append({"name": "Sign-in", "type": "Entra ID" if os.getenv("AAD_TENANT_ID") else "Demo user profiles", "status": "online" if os.getenv("AAD_TENANT_ID") else "built-in", "detail": "who is asking decides which documents they can see"})
    return rows

def overall(rows): return "down" if any(r["status"] == "down" for r in rows) else "online"

def ping_llm():
    """Live call to the configured AI provider (one tiny request). Returns (ok, message)."""
    try:
        if os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY"):
            from openai import AzureOpenAI
            c = AzureOpenAI(api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"), timeout=10); model = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        elif os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI
            c = OpenAI(timeout=10); model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        else:
            return False, "No AI key configured: using the built-in answer mode."
        t0 = time.perf_counter()
        r = c.chat.completions.create(model=model, max_tokens=5, messages=[{"role": "user", "content": "Reply with the word ok"}])
        return True, f"{model} replied in {(time.perf_counter() - t0) * 1000:.0f} ms"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
