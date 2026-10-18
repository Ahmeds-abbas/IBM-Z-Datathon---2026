"""Recorded Golden HOUR V3 Guardian+Granite dashboard bridge.

Displays decisions from an immutable historical-replay archive and verified Granite
output CSV. Never runs inference, touches banks, or reads laundering labels.

Usage: python3 -m v3.recorded_demo --archive ... --explanations ...
The existing v3.app serves /api/state and simulated approval/rejection.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from zipfile import ZipFile

from .app import AppServer, LiveStore, parse_time
from .explainer import validate_generated

DEFAULT_TIME = "2022-09-06T14:00:00Z"
ALLOWED_SOURCES = {
    "granite_heuristic_pass_human_review_required",
    "granite_rejected_or_unavailable_structured_fallback",
    "structured_template_no_llm",
}


def canon(value: str) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def load_checkpoint(archive: str | Path, requested_time: str) -> dict:
    stamp = canon(requested_time)
    matches = []
    with ZipFile(archive) as z:
        for name in z.namelist():
            if not name.startswith("expanded_guardian/decisions/") or not name.endswith(".json"):
                continue
            d = json.loads(z.read(name))
            if canon(d["decision_time"]) == stamp:
                matches.append(d)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Guardian checkpoint at {stamp}, found {len(matches)}")
    return matches[0]


def read_explanations(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        result = list(csv.DictReader(f))
    if not result:
        raise ValueError("Empty explanation CSV")
    return result


def compose(checkpoint: dict, rows: list[dict]) -> tuple[dict, dict[str, dict], str]:
    stamp = canon(checkpoint["decision_time"])
    now = parse_time(stamp)
    guardian = checkpoint["guardian_decision"]
    guardian_sha = guardian["decision_sha256"]
    original = checkpoint["recommendations"]
    if original != guardian["recommendations"]:
        raise ValueError("Inconsistent Guardian recommendations")
    if not (1 <= len(original) <= 10):
        raise ValueError("Recorded demo requires 1–10 Guardian recommendations")
    selected = {str(r["acct"]): r for r in original}
    if len(selected) != len(original):
        raise ValueError("Duplicate account in Guardian checkpoint")
    row_map = {str(r["acct"]): r for r in rows}
    if len(row_map) != len(rows) or set(row_map) != set(selected):
        raise ValueError("Explanation accounts must match the selected checkpoint exactly")
    explanations = {}
    recommendations = []
    scores = {str(x["acct"]): {"acct": str(x["acct"]),
                                 "risk_score": float(x["risk_score"]),
                                 "as_of": stamp, "reason_facts": ""}
              for x in checkpoint.get("computed_risk_only_top_k", [])}
    for acct, rec in selected.items():
        row = row_map[acct]
        if canon(row["decision_time"]) != stamp:
            raise ValueError(f"Wrong decision timestamp for {acct}")
        if row["decision_sha256"] != guardian_sha:
            raise ValueError(f"Wrong Guardian decision SHA for {acct}")
        if int(row["rank"]) != int(rec["rank"]):
            raise ValueError(f"Wrong Guardian rank for {acct}")
        if abs(float(row["risk_score"]) - float(rec["risk_score"])) > 1e-7:
            raise ValueError(f"Wrong Guardian score for {acct}")
        if row["reason_facts"] != rec["reason_facts"]:
            raise ValueError(f"Wrong Guardian evidence for {acct}")
        if str(row["requires_human_approval"]).lower() != "true" or rec.get("requires_human_approval") is not True:
            raise ValueError(f"Human approval missing for {acct}")
        if row["execution_status"] != "NOT_EXECUTED" or rec["execution_status"] != "NOT_EXECUTED":
            raise ValueError(f"Executed action in supposedly simulated demo: {acct}")
        if row["action"] != "ACCOUNT_REVIEW_RECOMMENDATION" or rec["action"] != "ACCOUNT_REVIEW_RECOMMENDATION":
            raise ValueError(f"Unsupported intervention action: {acct}")
        if canon(row["feature_cutoff"]) != canon(checkpoint["feature_cutoff"]):
            raise ValueError(f"Feature cutoff mismatch for {acct}")
        if canon(row["score_available_at"]) != canon(checkpoint["score_available_at"]):
            raise ValueError(f"Score availability mismatch for {acct}")
        if parse_time(row["feature_cutoff"]) > now or parse_time(row["score_available_at"]) > now:
            raise ValueError(f"Future-scored decision for {acct}")
        source = row["explanation_source"]
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"Unrecognised explanation source for {acct}: {source}")
        if not row["investigator_explanation"].strip():
            raise ValueError(f"Missing structured explanation for {acct}")
        text = row["investigator_explanation"]
        if source == "granite_heuristic_pass_human_review_required":
            draft = row["granite_draft"].strip()
            ok, note = validate_generated({"acct": acct, "as_of": stamp,
                                           "risk_score": float(rec["risk_score"]),
                                           "reason_facts": rec["reason_facts"]}, draft)
            if not ok:
                raise ValueError(f"Stored Granite draft did not pass current safety checks for {acct}: {note}")
            text = draft
        seconds = float(row.get("granite_seconds") or 0)
        explanations[acct] = {"status": "ready", "text": text, "source": source,
                              "note": (row.get("granite_validation_note") or "") +
                                      "; recorded historical-replay output, not live inference",
                              "seconds": seconds,
                              "review_status": "AI draft — human analyst review required" if source.startswith("granite_") and "heuristic_pass" in source else "Structured evidence — human review required"}
        recommendations.append({"acct": acct, "rank": int(rec["rank"]), "risk_score": float(rec["risk_score"]),
                                "as_of": stamp, "reason_facts": rec["reason_facts"],
                                "requires_human_approval": True})
        scores[acct] = {"acct": acct, "risk_score": float(rec["risk_score"]),
                        "as_of": stamp, "reason_facts": rec["reason_facts"]}
    payload = {
        "snapshot": {
            "as_of": stamp,
            "snapshot_id": guardian_sha[:24],
            "mode": "RECORDED_GUARDIAN_V3_NOT_LIVE",
            "total_seen": int(checkpoint["visible_tx_count"]),
            "watch_threshold": 0.8,
            # The checkpoint archive does not contain raw recent transaction rows
            # or a cross-bank link matrix. Do not invent either.
            "recent_transactions": [], "bank_links": []
        },
        "scores": list(scores.values()),
        "recommendations": recommendations,
    }
    return payload, explanations, guardian_sha


class RecordedStore(LiveStore):
    """Uses existing dashboard UI and immutable approval log with cached outputs."""
    def seed_recorded(self, checkpoint: dict, rows: list[dict]) -> dict:
        payload, by_acct, guardian_sha = compose(checkpoint, rows)
        result = self.publish(payload)
        with self._lock:
            self.current["guardian_decision_sha256"] = guardian_sha
            self.current["score_scope_note"] = "Only selected Guardian and recorded risk-only top-k scores are available here, not all model scores"
            self.current["transaction_detail_note"] = "Raw transaction list and bank-link matrix were not supplied in the checkpoint archive"
            for rec in self.current["recommendations"]:
                rec["guardian_decision_sha256"] = guardian_sha
                rec["execution_status"] = "NOT_EXECUTED"
                self.explanations[rec["decision_id"]] = by_acct[rec["acct"]]
        return result


def main():
    p = argparse.ArgumentParser(description="Recorded Guardian V3 dashboard; no inference or bank access")
    p.add_argument("--archive", required=True, help="Original Guardian 40-checkpoint ZIP")
    p.add_argument("--explanations", required=True, help="Granite checkpoint CSV created on LinuxONE")
    p.add_argument("--checkpoint", default=DEFAULT_TIME)
    p.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--audit", default="v3/recorded_demo_audit.jsonl")
    args = p.parse_args()
    data = load_checkpoint(args.archive, args.checkpoint)
    rows = read_explanations(args.explanations)
    store = RecordedStore(args.audit)
    result = store.seed_recorded(data, rows)
    server = AppServer((args.host, args.port), store)
    print(f"Golden HOUR V3 RECORDED checkpoint ready on {args.host}:{args.port}", flush=True)
    print(f"Guardian time: {result['as_of']}; recommendations: {result['recommendations']}", flush=True)
    print("Prevalidated explanations imported from CSV; NO MODEL INFERENCE and NO BANK HOLDS", flush=True)
    print("Notes: historical 2022 replay; model trained in 2026; risk-score subset only", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
