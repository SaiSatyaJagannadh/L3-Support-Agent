"""Ingestion worker: crawl -> chunk on headings (~500-800 tokens) -> index. Run as AKS CronJob.
Crawler is env-gated (CONFLUENCE_URL, CONFLUENCE_USER, CONFLUENCE_TOKEN); other sources follow the same shape."""
import os, re, httpx

def chunk(text, max_words=600):
    parts = re.split(r"\n(?=#{1,3} )", text); out = []
    for p in parts:
        w = p.split()
        out += [" ".join(w[i:i + max_words]) for i in range(0, len(w), max_words)] or []
    return [c for c in out if c]

def crawl_confluence(space):
    base = os.environ["CONFLUENCE_URL"]
    r = httpx.get(f"{base}/rest/api/content", params={"spaceKey": space, "expand": "body.storage,restrictions.read.restrictions.group"},
                  auth=(os.environ["CONFLUENCE_USER"], os.environ["CONFLUENCE_TOKEN"]), timeout=30); r.raise_for_status()
    return [{"id": f"cf-{p['id']}-{i}", "source": "confluence", "url": f"{base}{p['_links']['webui']}", "acl": ["staff"],  # TODO map space perms -> Entra groups
             "text": c} for p in r.json()["results"] for i, c in enumerate(chunk(re.sub(r"<[^>]+>", " ", p["body"]["storage"]["value"])))]

def run(index):  # index = core.KB list (stand-in for AI Search upload)
    if os.getenv("CONFLUENCE_URL"): index += crawl_confluence(os.getenv("CONFLUENCE_SPACE", "L3"))
    return len(index)
