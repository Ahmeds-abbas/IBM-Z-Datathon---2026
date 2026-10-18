"""Small client adapter for the other Golden HOUR V3 components."""
from __future__ import annotations
import json
import os
from time import perf_counter
from urllib.request import Request, urlopen

def publish_snapshot(snapshot: dict, scores: list[dict], recommendations: list[dict],
                     url: str = "http://127.0.0.1:8765/api/publish") -> dict:
    """Send already time-correct outputs to the local UI; never uses labels."""
    body = json.dumps({"snapshot": snapshot, "scores": scores,
                       "recommendations": recommendations}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("GH_V3_INGEST_TOKEN")
    if secret:
        headers["X-Ingest-Token"] = secret
    request = Request(url, data=body, headers=headers, method="POST")
    t = perf_counter()
    with urlopen(request, timeout=10) as response:
        result = json.load(response)
    result["ui_publish_roundtrip_ms"] = round((perf_counter() - t) * 1000, 3)
    return result
