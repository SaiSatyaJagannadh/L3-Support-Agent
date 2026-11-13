"""Tiny load test: python3 loadtest.py http://localhost:8000 [n=100] (stand-in for Azure Load Testing)."""
import sys, time, httpx
from concurrent.futures import ThreadPoolExecutor
url, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100
def one(_):
    t = time.time(); r = httpx.post(f"{url}/chat", json={"message": "payflow prod 504 timeout"}, timeout=30); return r.status_code, time.time() - t
with ThreadPoolExecutor(10) as ex: res = list(ex.map(one, range(n)))
lat = sorted(x[1] for x in res); print(f"ok={sum(r[0]==200 for r in res)}/{n} p50={lat[n//2]*1000:.0f}ms p95={lat[int(n*.95)]*1000:.0f}ms")
