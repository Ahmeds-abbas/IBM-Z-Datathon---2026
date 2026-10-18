"""Golden HOUR V3 local investigator UI (stdlib HTTP server).

Inputs: POST /api/publish with {snapshot, scores, recommendations}; see mock_feed.py.
This UI does NOT run detection, optimisation, or a bank hold. It only displays
current-state recommendations and records simulated investigator choices.
Bind to 127.0.0.1 and access through authenticated Jupyter proxy if installed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import threading
import time
from urllib.parse import urlparse

try:
    from .explainer import GraniteExplainer, evidence_key
except ImportError:
    from explainer import GraniteExplainer, evidence_key

HERE = Path(__file__).resolve().parent
BANNED = {"is_laundering", "ground_truth", "laundering_label", "future_transactions",
          "eval_only_laundering", "observed_laundering_touched_usd"}
MAX_BODY = 800_000


def check_no_labels(obj, path="payload"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in BANNED or k.lower().startswith("eval_only_"):
                raise ValueError(f"decision payload contains evaluation-only field: {path}.{k}")
            check_no_labels(v, path + "." + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            check_no_labels(v, path + f"[{i}]")


def parse_time(s):
    if not isinstance(s, str) or not s:
        raise ValueError("missing as_of UTC timestamp")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("as_of and event times must be timezone aware")
    return dt.astimezone(timezone.utc)


def validate_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    check_no_labels(data)
    snap = data.get("snapshot")
    if not isinstance(snap, dict):
        raise ValueError("snapshot object required")
    as_of = snap.get("as_of")
    now = parse_time(as_of)
    scores = data.get("scores", [])
    recommendations = data.get("recommendations", [])
    if not isinstance(scores, list) or not isinstance(recommendations, list):
        raise ValueError("scores and recommendations must be lists")
    if len(scores) > 120_000 or len(recommendations) > 10:
        raise ValueError("too many scores or >10 intervention recommendations")
    seen = set()
    normalized_scores = []
    for r in scores:
        if not isinstance(r, dict) or not r.get("acct"):
            raise ValueError("invalid risk record")
        acct = str(r["acct"])
        if acct in seen:
            raise ValueError("duplicate risk account")
        seen.add(acct)
        try:
            risk = float(r["risk_score"])
        except (TypeError, ValueError, KeyError):
            raise ValueError("invalid risk score") from None
        if not (0 <= risk <= 1):
            raise ValueError("risk score outside [0,1]")
        if "as_of" in r and parse_time(r["as_of"]) != now:
            raise ValueError("risk score timestamp must equal snapshot time")
        normalized_scores.append({"acct": acct, "risk_score": risk,
                                  "reason_facts": str(r.get("reason_facts", ""))[:850]})
    score_map = {r["acct"]: r["risk_score"] for r in normalized_scores}
    chosen = []
    ranks = set()
    for r in recommendations:
        if not isinstance(r, dict):
            raise ValueError("recommendation must be an object")
        acct = str(r.get("acct", ""))
        if acct not in score_map or any(x["acct"] == acct for x in chosen):
            raise ValueError("recommended account missing from scores or duplicated")
        if r.get("requires_human_approval") is not True:
            raise ValueError("every recommendation requires human approval")
        if "as_of" in r and parse_time(r["as_of"]) != now:
            raise ValueError("recommendation timestamp must equal snapshot time")
        rank = int(r.get("rank", len(chosen) + 1))
        if rank in ranks or not (1 <= rank <= 10):
            raise ValueError("invalid recommendation rank")
        ranks.add(rank)
        if "risk_score" in r and abs(float(r["risk_score"]) - score_map[acct]) > 1e-7:
            raise ValueError("Guardian risk score does not match detector")
        facts = str(r.get("reason_facts", ""))[:850]
        chosen.append({"acct": acct, "rank": rank, "risk_score": score_map[acct],
                       "as_of": as_of, "reason_facts": facts,
                       "requires_human_approval": True})
    chosen.sort(key=lambda x: x["rank"])
    recent = snap.get("recent_transactions", [])
    if not isinstance(recent, list) or len(recent) > 200:
        raise ValueError("recent_transactions must be a list of at most 200")
    txs = []
    seen_txs = set()
    for tx in recent:
        if not isinstance(tx, dict) or not tx.get("tx_id"):
            raise ValueError("transaction requires tx_id")
        ident = str(tx["tx_id"])
        if ident in seen_txs:
            raise ValueError("duplicate transaction ID in snapshot")
        seen_txs.add(ident)
        ts = tx.get("timestamp")
        if not ts or parse_time(ts) > now:
            raise ValueError("future or missing transaction timestamp")
        txs.append({k: str(tx.get(k, ""))[:100] for k in (
            "tx_id", "timestamp", "from_acct", "to_acct", "from_bank", "to_bank", "currency")})
    links = snap.get("bank_links", [])
    if not isinstance(links, list) or len(links) > 12:
        raise ValueError("bank_links must be a list of at most 12")
    safe_links = []
    for link in links:
        if not isinstance(link, dict) or int(link.get("count", 0)) < 0:
            raise ValueError("invalid bank link")
        safe_links.append({"from_bank": str(link.get("from_bank", ""))[:40],
                           "to_bank": str(link.get("to_bank", ""))[:40],
                           "count": int(link.get("count", 0))})
    mode = str(snap.get("mode", "unverified_source"))[:64]
    # Watchlist can contain more than ten; max 40 sent to browser for modest memory.
    threshold = float(snap.get("watch_threshold", 0.8))
    watchlist = sorted((r for r in normalized_scores if r["risk_score"] >= threshold),
                       key=lambda r: (-r["risk_score"], r["acct"]))
    watch_count = len(watchlist)
    return {"as_of": as_of, "snapshot_id": str(snap.get("snapshot_id", as_of))[:100],
            "mode": mode, "total_seen": int(snap.get("total_seen", len(txs))),
            "watch_count": watch_count, "watchlist": watchlist[:40],
            "scores_count": len(scores), "recommendations": chosen,
            "recent_transactions": txs[-25:], "bank_links": safe_links,
            "published_seconds": time.time()}


class LiveStore:
    def __init__(self, audit_path: str | Path, explainer: GraniteExplainer | None = None):
        self._lock = threading.RLock()
        self.current: dict | None = None
        self.sequence = 0
        self.decisions: dict[str, dict] = {}
        self.explanations: dict[str, dict] = {}
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.explainer = explainer or GraniteExplainer()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="granite")

    @staticmethod
    def decision_id(record: dict) -> str:
        return sha256((record["as_of"] + "|" + record["acct"] + "|" +
                       evidence_key(record)).encode()).hexdigest()[:24]

    def publish(self, payload: dict) -> dict:
        normalized = validate_payload(payload)
        with self._lock:
            if self.current and parse_time(normalized["as_of"]) < parse_time(self.current["as_of"]):
                raise ValueError("cannot publish a snapshot older than the current decision time")
            self.sequence += 1
            normalized["sequence"] = self.sequence
            for rec in normalized["recommendations"]:
                rec["decision_id"] = self.decision_id(rec)
                rec["review_status"] = self.decisions.get(rec["decision_id"], {}).get(
                    "action", "awaiting_human_review")
            self.current = normalized
            return {"sequence": self.sequence, "as_of": normalized["as_of"],
                    "recommendations": len(normalized["recommendations"])}

    def state(self) -> dict:
        with self._lock:
            if self.current is None:
                return {"ready": False, "message": "Waiting for a live-replay snapshot"}
            data = json.loads(json.dumps(self.current))  # immutable response copy
            for rec in data["recommendations"]:
                did = rec["decision_id"]
                rec["explanation"] = self.explanations.get(did, {"status": "not_requested"})
                rec["review_status"] = self.decisions.get(did, {}).get("action", "awaiting_human_review")
            return {"ready": True, **data}

    def _record(self, record: dict) -> None:
        with self.audit_path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, sort_keys=True) + "\n")
            out.flush()

    def _get_rec(self, acct: str, decision_id: str) -> dict:
        if not self.current:
            raise ValueError("no current recommendations")
        match = next((r for r in self.current["recommendations"]
                      if r["acct"] == acct and r["decision_id"] == decision_id), None)
        if not match:
            raise ValueError("stale or unknown recommendation")
        return dict(match)

    def decide(self, acct: str, decision_id: str, action: str) -> dict:
        if action not in {"approve", "reject"}:
            raise ValueError("action must be approve or reject")
        with self._lock:
            record = self._get_rec(acct, decision_id)
            if decision_id in self.decisions:
                raise ValueError("already reviewed; decision is immutable")
            event = {"event": "simulated_investigator_decision", "action": action,
                     "acct": acct, "decision_id": decision_id,
                     "as_of": record["as_of"], "evidence_hash": evidence_key(record),
                     "recorded_utc": datetime.now(timezone.utc).isoformat(),
                     "note": "No real account hold was applied"}
            self._record(event)
            self.decisions[decision_id] = event
            return event

    def request_explanation(self, acct: str, decision_id: str) -> dict:
        with self._lock:
            record = self._get_rec(acct, decision_id)
            existing = self.explanations.get(decision_id)
            if existing:
                return existing
            self.explanations[decision_id] = {"status": "queued"}
        self.pool.submit(self._work_explanation, record, decision_id)
        return {"status": "queued"}

    def _work_explanation(self, rec: dict, did: str) -> None:
        # Another thread serves alerts immediately while Granite generates.
        try:
            result = self.explainer.explain(rec).as_dict()
            value = {"status": "ready", **result}
        except Exception as exc:
            # A crashed worker is not allowed to break the alert loop.
            value = {"status": "error", "note": type(exc).__name__}
        with self._lock:
            self.explanations[did] = value


class Handler(BaseHTTPRequestHandler):
    server: "AppServer"

    def log_message(self, fmt, *args):
        if os.getenv("GH_V3_LOG_HTTP") == "1":
            super().log_message(fmt, *args)

    def reply(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/dashboard"}:
            data = (HERE / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/state":
            self.reply(200, self.server.store.state())
        elif path == "/api/health":
            self.reply(200, {"ok": True, "service": "golden-hour-v3-investigator"})
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/publish", "/api/explain", "/api/decision"}:
            return self.reply(404, {"error": "not found"})
        # Reject obvious cross-site browser POSTs. Host is the authenticated proxy's host.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.reply(403, {"error": "cross-origin request forbidden"})
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if size < 0 or size > MAX_BODY:
                return self.reply(413, {"error": "invalid request size"})
            content = self.rfile.read(size)
            request = json.loads(content)
            if not isinstance(request, dict):
                raise ValueError("JSON object required")
            if path == "/api/publish":
                secret = os.getenv("GH_V3_INGEST_TOKEN")
                if secret:
                    from hmac import compare_digest
                    if not compare_digest(self.headers.get("X-Ingest-Token", ""), secret):
                        return self.reply(403, {"error": "invalid ingest token"})
                return self.reply(200, self.server.store.publish(request))
            acct, did = str(request.get("acct", "")), str(request.get("decision_id", ""))
            if path == "/api/explain":
                return self.reply(202, self.server.store.request_explanation(acct, did))
            return self.reply(200, self.server.store.decide(acct, did, request.get("action")))
        except ValueError as exc:
            self.reply(409, {"error": str(exc)})
        except (TypeError, KeyError, json.JSONDecodeError):
            self.reply(400, {"error": "invalid request"})


class AppServer(ThreadingHTTPServer):
    def __init__(self, address, store: LiveStore):
        super().__init__(address, Handler)
        self.store = store


def main():
    parser = argparse.ArgumentParser(description="Golden HOUR V3 — local investigator UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--audit", default="v3/decision_audit.jsonl")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("GH_V3_INGEST_TOKEN"):
        parser.error("Non-loopback binding requires GH_V3_INGEST_TOKEN; do not expose this demo publicly")
    server = AppServer((args.host, args.port), LiveStore(args.audit))
    print(f"Golden HOUR V3 listening on http://{args.host}:{args.port}", flush=True)
    print("Mock feed: python -m v3.mock_feed; demo-only, no real customer intervention", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
