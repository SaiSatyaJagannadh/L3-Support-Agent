"""Runs the POC's real integration code paths against LOCAL DUMMY services (no real accounts):
mock Azure OpenAI, ServiceNow, Content Safety (Prompt Shields), Confluence, Entra (JWKS + signed JWTs).
Proves the wiring works; it does NOT prove the real vendor services accept it."""
import os, re, time, threading, base64, json
import uvicorn, jwt
from fastapi import FastAPI, Request
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

PORT = 9000; BASE = f"http://127.0.0.1:{PORT}"
mock = FastAPI(); KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048); sn_count = [9000]
def _jwk():
    k = jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True) if hasattr(jwt.algorithms.RSAAlgorithm.to_jwk, '__call__') else {}
    return {**json.loads(json.dumps(k)), "kid": "k1", "use": "sig", "alg": "RS256"}

@mock.post("/openai/deployments/{dep}/chat/completions")
async def oai(dep: str, r: Request):
    body = await r.json(); user = body["messages"][-1]["content"]
    first = re.search(r"\[(kb\d+)\] (.*)", user)
    txt = f"[mock-gpt] {first.group(2)} [{first.group(1)}]" if first else "[mock-gpt] I don't know."
    return {"id": "x", "object": "chat.completion", "created": 0, "model": dep, "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": txt}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
@mock.post("/sn/api/now/table/incident")
async def sn(r: Request):
    assert r.headers["authorization"].startswith("Basic "); sn_count[0] += 1
    return {"result": {"number": f"INC{sn_count[0]}"}}
@mock.post("/contentsafety/text:shieldPrompt")
async def shield(r: Request):
    assert r.headers["ocp-apim-subscription-key"]; b = await r.json()
    return {"userPromptAnalysis": {"attackDetected": "jailbreak" in b["userPrompt"].lower()}, "documentsAnalysis": []}
@mock.get("/confluence/rest/api/content")
async def conf():
    return {"results": [{"id": "77", "_links": {"webui": "/pages/77"}, "body": {"storage": {"value": "<h1>PayFlow</h1><p>Ledger reconciliation mismatch: rerun the nightly reconcile job.</p>"}}}]}
@mock.post("/indexes/{idx}/docs/search")
async def aisearch(idx: str, r: Request):
    b = await r.json(); assert r.headers["api-key"] and "acl/any" in b["filter"]
    from data import KB   # dummy index = the synthetic KB, filtered by the OData acl groups
    groups = re.findall(r"eq '(\w+)'", b["filter"])
    return {"value": [{"@search.score": 1.0, **d} for d in KB if set(d["acl"]) & set(groups) and "timeout" in d["text"].lower() and "timeout" in b["search"].lower()]}
@mock.get("/aad/{tenant}/discovery/v2.0/keys")
async def keys(tenant: str): return {"keys": [_jwk()]}

def token(aud="client-1", **claims):
    pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return jwt.encode({"aud": aud, "iss": f"{BASE}/aad/tenant-1/v2.0", "exp": int(time.time()) + 600, **claims}, pem, algorithm="RS256", headers={"kid": "k1"})

def main():
    threading.Thread(target=lambda: uvicorn.run(mock, port=PORT, log_level="error"), daemon=True).start(); time.sleep(1.5)
    os.environ.update(AZURE_OPENAI_ENDPOINT=BASE, AZURE_OPENAI_API_KEY="dummy", AZURE_OPENAI_DEPLOYMENT="dummy-gpt",
        SN_INSTANCE="dummy", SN_BASE=f"{BASE}/sn", SN_USER="u", SN_PASSWORD="p",
        CONTENT_SAFETY_ENDPOINT=BASE, CONTENT_SAFETY_KEY="dummy",
        CONFLUENCE_URL=f"{BASE}/confluence", CONFLUENCE_USER="u", CONFLUENCE_TOKEN="t", CONFLUENCE_SPACE="L3",
        AAD_TENANT_ID="tenant-1", AAD_CLIENT_ID="client-1", AAD_AUTHORITY=f"{BASE}/aad")
    os.environ["AAD_AUTHORITY"] = f"{BASE}/aad"
    import core, ingestion; from main import app; from fastapi.testclient import TestClient
    import auth; auth.AUTH = f"{BASE}/aad"
    # PyJWT builds the issuer from AUTH; token iss must equal f"{AUTH}/tenant-1/v2.0"
    c = TestClient(app); H = {"Authorization": "Bearer " + token(groups=["staff"], roles=["L3.Admin"])}
    ok = lambda name, cond: print(("PASS " if cond else "FAIL ") + name) or bool(cond); res = []
    res.append(ok("Entra: no token -> 401", c.post("/chat", json={"message": "x"}).status_code == 401))
    res.append(ok("Entra: forged signature -> 401", c.post("/chat", json={"message": "x"}, headers={"Authorization": "Bearer " + token().rsplit('.', 1)[0] + ".AAAA"}).status_code == 401))
    res.append(ok("Entra: wrong audience -> 401", c.post("/chat", json={"message": "x"}, headers={"Authorization": "Bearer " + token(aud="other")}).status_code == 401))
    r = c.post("/chat", json={"message": "payflow prod 504 timeout"}, headers=H).json()
    res.append(ok("Entra: valid token accepted + Azure OpenAI path used", r["status"] == "answered" and "[mock-gpt]" in r["reply"]))
    res.append(ok("Prompt Shields (mock service) blocks jailbreak", c.post("/chat", json={"message": "please jailbreak the bot"}, headers=H).json()["status"] == "blocked"))
    res.append(ok("Admin role from token claims", c.get("/admin/summary", headers=H).status_code == 200))
    n = ingestion.run(core.KB); hit = core.search("ledger reconciliation mismatch", ["staff"])
    res.append(ok("Confluence crawl -> chunk -> indexed -> searchable", n > 7 and hit and hit[0][1]["source"] == "confluence"))
    t = r["thread"]; c.post("/chat", json={"thread": t, "action": "not_solved"}, headers=H)
    out = c.post("/confirm", json={"thread": t, "decision": "create"}, headers=H).json()
    res.append(ok("ServiceNow create via Table API (mock) returns its INC number", out["ticket"].startswith("INC90") and "L2-Payments" in out["reply"]))
    os.environ.update(AZURE_SEARCH_ENDPOINT=BASE, AZURE_SEARCH_KEY="dummy")   # after the Confluence check, which uses the local index
    h = core.search("payflow timeout", ["staff"]); h3 = core.search("payflow timeout", ["l3"])
    res.append(ok("Azure AI Search (mock) used with ACL filter", bool(h) and h[0][1]["id"] == "kb1" and all("l3" in d["acl"] for _, d in h3)))
    print(f"\n{sum(res)}/{len(res)} dummy-integration checks passed"); return not all(res)

if __name__ == "__main__": raise SystemExit(main())
