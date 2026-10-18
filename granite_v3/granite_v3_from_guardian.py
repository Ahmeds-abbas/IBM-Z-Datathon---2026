#!/usr/bin/env python3
"""Golden HOUR V3 | audited Guardian decision -> investigator explanation handoff.

No laundering label file, full transaction source or live banking service is read.
Structured explanations can be built offline; optional Granite drafts run on LinuxONE.
The optional generative check is heuristic, NOT a proof of semantic correctness.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import math
import re
from pathlib import Path
import sys
from zipfile import ZipFile

DECISION_PATTERN = re.compile(r"^expanded_guardian/decisions/(\d{8}T\d{6}Z)\.json$")
ACCOUNT_PATTERN = re.compile(r"^A_[A-Za-z0-9]+$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
FACT_PATTERNS = {
    "historical": re.compile(r"(\d+) historical transfers", re.I),
    "counterparties": re.compile(r"(\d+) counterparties", re.I),
    "cross_bank": re.compile(r"(\d+) cross-bank transfers", re.I),
}
COLS = [
    "acct", "rank", "decision_time", "feature_cutoff", "score_available_at",
    "decision_sha256", "model_sha256", "risk_score", "reason_facts",
    "observation_start", "incoming_tx", "outgoing_tx",
    "est_money_blocked", "estimated_proxy_collateral", "marginal_gross_touched_usd",
    "action", "execution_status", "requires_human_approval",
    "investigator_explanation", "granite_draft", "explanation_source", "granite_seconds",
    "granite_validation_note", "evidence_key",
]


def ensure(cond: bool, message: str) -> None:
    if not cond:
        raise ValueError(message)


def parse_dt(value: str) -> datetime:
    ensure(isinstance(value, str), "timestamp must be a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    ensure(dt.tzinfo is not None, "timestamp missing timezone")
    return dt.astimezone(timezone.utc)


def text_date(value: str) -> str:
    return parse_dt(value).strftime("%Y-%m-%d %H:%M UTC")


def fact_counts(facts: str) -> dict[str, int]:
    vals = {}
    for k, pattern in FACT_PATTERNS.items():
        m = pattern.search(facts)
        ensure(m is not None, f"missing {k} in reason_facts")
        vals[k] = int(m.group(1))
    return vals


def validate_decision(obj: dict, filename: str) -> None:
    dt = parse_dt(obj["decision_time"])
    ensure(DECISION_PATTERN.fullmatch(filename) is not None, "unrecognised decision path")
    ensure(dt.strftime("%Y%m%dT%H%M%SZ") in filename, "decision timestamp/filename mismatch")
    ensure(obj.get("time_domain") == "historical_event_time_simulation", "unsupported time domain")
    ensure(parse_dt(obj["feature_cutoff"]) <= dt, "future feature cutoff")
    ensure(parse_dt(obj["score_available_at"]) <= dt, "future score available")
    dec = obj["guardian_decision"]
    identifier = dec["decision_sha256"]
    ensure(isinstance(identifier, str) and HEX_64.fullmatch(identifier) is not None, "invalid decision ID")
    ensure(parse_dt(dec["decision_time"]) == dt, "nested decision_time mismatch")
    ensure(obj["recommendations"] == dec["recommendations"], "decision recommendation mismatch")
    ensure([r["acct"] for r in obj["recommendations"]] == obj["selected_accounts"], "selected-account mismatch")
    ensure(len(obj["recommendations"]) <= 10, "Guardian review budget exceeded")
    ensure(len({r["acct"] for r in obj["recommendations"]}) == len(obj["recommendations"]), "duplicate account at checkpoint")
    ensure(isinstance(obj["model_sha256"], str) and HEX_64.fullmatch(obj["model_sha256"]) is not None, "invalid model ID")
    for idx, rec in enumerate(obj["recommendations"], start=1):
        ensure(ACCOUNT_PATTERN.fullmatch(rec["acct"]) is not None, "invalid account ID")
        ensure(rec["rank"] == idx, "recommendation rank inconsistent")
        ensure(parse_dt(rec["decision_time"]) == dt, "recommendation time mismatch")
        ensure(parse_dt(rec["observation_start"]) <= dt, "future observation start")
        ensure(rec["action"] == "ACCOUNT_REVIEW_RECOMMENDATION", "unexpected Guardian action")
        ensure(rec["execution_status"] == "NOT_EXECUTED", "unexpected executed action")
        ensure(rec["requires_human_approval"] is True, "human approval missing")
        score = float(rec["risk_score"])
        ensure(math.isfinite(score) and 0 <= score <= 1, "invalid risk score")
        facts = rec["reason_facts"]
        ensure(isinstance(facts, str) and "HUMAN REVIEW ONLY" in facts, "unbounded facts")
        counts = fact_counts(facts)
        assert counts
        found = re.search(r"Risk score\s+(\d+\.\d{3})(?!\d)", facts)
        ensure(found is not None and abs(float(found.group(1)) - score) <= 0.000501,
               "risk score/reason_facts mismatch")
        for key in ("est_money_blocked", "estimated_proxy_collateral", "marginal_gross_touched_usd"):
            number = float(rec[key])
            ensure(math.isfinite(number) and number >= 0, f"invalid {key}")


def load_archive(path: Path):
    ensure(path.is_file(), f"archive not found: {path}")
    with ZipFile(path) as z:
        ensure(z.testzip() is None, "corrupted ZIP archive")
        paths = sorted(n for n in z.namelist() if DECISION_PATTERN.fullmatch(n))
        ensure(bool(paths), "no Guardian decision JSON files")
        ensure("expanded_guardian/expanded_status.json" in z.namelist(), "missing run status")
        status = json.loads(z.read("expanded_guardian/expanded_status.json"))
        ensure(status.get("status") == "PASS", "archive reports failed run")
        docs = []
        for filename in paths:
            obj = json.loads(z.read(filename))
            validate_decision(obj, filename)
            docs.append(obj)
        ensure(status.get("checkpoints_completed") == len(docs), "status checkpoint count mismatch")
    ids = [d["guardian_decision"]["decision_sha256"] for d in docs]
    ensure(len(ids) == len(set(ids)), "duplicate checkpoint decision identifier")
    return docs, status


def usd(value: float) -> str:
    return f"USD {value:,.0f}"


def readable_noun(n: int, noun: str) -> str:
    plural = "counterparties" if noun == "counterparty" else noun + "s"
    return f"{n} {noun if n == 1 else plural}"


def structured_explanation(rec: dict, decision_time: str) -> str:
    counts = fact_counts(rec["reason_facts"])
    return (
        f"At {text_date(decision_time)}, Guardian prioritised account {rec['acct']} "
        f"for investigator review (rank {rec['rank']}; account-level risk score "
        f"{float(rec['risk_score']):.3f}, not a probability of crime). "
        f"The observed window records {readable_noun(counts['historical'], 'historical transfer')}, "
        f"{readable_noun(counts['counterparties'], 'counterparty')}, and "
        f"{readable_noun(counts['cross_bank'], 'cross-bank transfer')}. "
        f"Guardian recorded a capped suspicion-exposure proxy of approximately "
        f"{usd(float(rec['est_money_blocked']))} and an uncalibrated legitimate-exposure "
        f"proxy of approximately {usd(float(rec['estimated_proxy_collateral']))}. "
        "These are decision-support estimates, not confirmed criminal funds, money recovered, "
        "or actual customer losses. The indicators do not prove money laundering. "
        "This is a recommendation for human review only; no account hold was executed."
    )


def make_explainer(explainer_path: Path, model_path: str | None):
    ensure(explainer_path.is_file(), f"Ahmed's explainer not found: {explainer_path}")
    spec = importlib.util.spec_from_file_location("golden_hour_v3_ahmed_explainer", explainer_path)
    ensure(spec is not None and spec.loader is not None, "could not import explainer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.GraniteExplainer(model_path=model_path)


def build_rows(docs: list[dict], *, use_granite: bool,
               explainer_path: Path, model_path: str | None, limit: int | None):
    explainer = make_explainer(explainer_path, model_path) if use_granite else None
    rows = []
    for obj in docs:
        dec_hash = obj["guardian_decision"]["decision_sha256"]
        for rec in obj["recommendations"]:
            assert parse_dt(rec["decision_time"]) == parse_dt(obj["decision_time"])
            payload = {
                "acct": rec["acct"], "as_of": obj["decision_time"],
                "risk_score": rec["risk_score"], "reason_facts": rec["reason_facts"],
            }
            key = sha256(json.dumps({"decision": dec_hash, "account": rec["acct"],
                                     "evidence": payload}, sort_keys=True).encode()).hexdigest()
            raw = ""
            source = "structured_template_no_llm"
            note = "Deterministic explanation from Guardian's recorded decision only; no Granite inference."
            seconds = ""
            if explainer is not None:
                result = explainer.explain(payload)
                source, note, seconds = result.source, result.note, result.seconds
                if source == "granite":
                    raw = result.text
                    source = "granite_heuristic_pass_human_review_required"
                else:
                    # Never place a non-model template in a column named granite_draft.
                    raw = ""
                    source = "granite_rejected_or_unavailable_structured_fallback"
            row = {"acct": rec["acct"], "rank": rec["rank"],
                   "decision_time": obj["decision_time"], "feature_cutoff": obj["feature_cutoff"],
                   "score_available_at": obj["score_available_at"],
                   "decision_sha256": dec_hash, "model_sha256": obj["model_sha256"],
                   "risk_score": rec["risk_score"], "reason_facts": rec["reason_facts"],
                   "observation_start": rec["observation_start"],
                   "incoming_tx": rec["incoming_tx"], "outgoing_tx": rec["outgoing_tx"],
                   "est_money_blocked": rec["est_money_blocked"],
                   "estimated_proxy_collateral": rec["estimated_proxy_collateral"],
                   "marginal_gross_touched_usd": rec["marginal_gross_touched_usd"],
                   "action": rec["action"], "execution_status": rec["execution_status"],
                   "requires_human_approval": rec["requires_human_approval"],
                   "investigator_explanation": structured_explanation(rec, obj["decision_time"]),
                   "granite_draft": raw, "explanation_source": source,
                   "granite_seconds": seconds, "granite_validation_note": note,
                   "evidence_key": key}
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                return rows
    return rows


def verify_rows(rows: list[dict], docs: list[dict], expected: int | None, granite_requested: bool):
    src_map = {(obj["decision_time"], rec["acct"]): (obj, rec)
               for obj in docs for rec in obj["recommendations"]}
    issues = []
    seen = set()
    for row in rows:
        key = (row["decision_time"], row["acct"])
        if key in seen:
            issues.append("duplicate account/checkpoint " + str(key))
            continue
        seen.add(key)
        if key not in src_map:
            issues.append("not in Guardian decisions " + str(key))
            continue
        obj, rec = src_map[key]
        for field in ("rank", "risk_score", "reason_facts", "action", "execution_status",
                      "requires_human_approval", "est_money_blocked", "estimated_proxy_collateral",
                      "marginal_gross_touched_usd", "observation_start"):
            if row[field] != rec[field]:
                issues.append("mismatched " + field + " " + str(key))
        if row["decision_sha256"] != obj["guardian_decision"]["decision_sha256"]:
            issues.append("decision hash mismatch " + str(key))
        explanation = row["investigator_explanation"]
        counts = fact_counts(rec["reason_facts"])
        for label, val in (("historical transfer", counts["historical"]),
                           ("counterparty", counts["counterparties"]),
                           ("cross-bank transfer", counts["cross_bank"])):
            if readable_noun(val, label) not in explanation:
                issues.append("fact mismatch " + label + " " + str(key))
        for text in (rec["acct"], f"{float(rec['risk_score']):.3f}",
                     usd(rec["est_money_blocked"]), usd(rec["estimated_proxy_collateral"])):
            if text not in explanation:
                issues.append("missing verified fact " + str(key))
        if "do not prove money laundering" not in explanation or "no account hold was executed" not in explanation:
            issues.append("missing uncertainty/simulated status " + str(key))
        if not explanation.strip():
            issues.append("empty explanation " + str(key))
    if expected is not None and len(rows) != expected:
        issues.append(f"row count expected {expected} got {len(rows)}")
    types = {}
    for r in rows:
        t = r["explanation_source"]
        types[t] = types.get(t, 0) + 1
    return {
        "status": "PASS" if not issues else "FAIL", "verification_scope": "record-to-output checks; "
        "not independent verification of original model, Guardian optimisation or Granite semantic correctness",
        "input_checkpoints_available": len(docs),
        "input_recommendations_available": len(src_map),
        "output_explanation_count": len(rows),
        "unique_explained_accounts": len({r["acct"] for r in rows}),
        "unique_decisions_explained": len({r["decision_sha256"] for r in rows}),
        "explanation_source_counts": types,
        "granite_requested": granite_requested,
        "granite_request_attempted": bool(granite_requested and rows),
        "granite_model_generation_confirmed": types.get("granite_heuristic_pass_human_review_required", 0) > 0,
        "granite_validated_drafts": types.get("granite_heuristic_pass_human_review_required", 0),
        "failures": issues[:60],
        "notes": [
            "Historical event-time replay of synthetic transaction data; no live bank connection.",
            "2026-trained model is not a model actually deployed during 2022.",
            "No laundering labels used to prepare these explanations.",
            "Guardian proxy values are not actual holds, recoveries or quantified confirmed losses.",
            "Granite output, if generated, is a separate draft; structured explanations remain the conservative investigator view.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path, help="Guardian 40-checkpoint ZIP")
    p.add_argument("--output", required=True, type=Path, help="output folder; V2 is never modified")
    p.add_argument("--checkpoint", help="e.g. 2022-09-06T14:00:00Z; omit for all 40")
    p.add_argument("--limit", type=int, help="cap number of recommendations explained, e.g. 1 for first Granite smoke test")
    p.add_argument("--granite", action="store_true", help="opt-in Granite llama_cpp inference; may use >1GB RAM")
    p.add_argument("--explainer-file", type=Path,
                   default=Path("/home/ibm-user/golden-hour-v3-ahmed-test/v3/explainer.py"),
                   help="Ahmed's tested V3 explainer.py")
    p.add_argument("--model-path", help="optional GGUF model location")
    a = p.parse_args(argv)
    if a.limit is not None and a.limit < 1:
        p.error("--limit must be a positive integer")
    docs, status = load_archive(a.source)
    if a.checkpoint:
        target = parse_dt(a.checkpoint)
        docs = [d for d in docs if parse_dt(d["decision_time"]) == target]
        ensure(bool(docs), f"checkpoint not found: {a.checkpoint}")
    rows = build_rows(docs, use_granite=a.granite, explainer_path=a.explainer_file,
                      model_path=a.model_path, limit=a.limit)
    expected = None if a.limit is not None else sum(len(x["recommendations"]) for x in docs)
    report = verify_rows(rows, docs, expected, a.granite)
    if a.granite and a.limit is None and len(rows) > 10:
        print("NOTE: full Granite inference requested; this can take many minutes on LinuxONE.", file=sys.stderr)
    ensure(report["status"] == "PASS", "verification failed: " + repr(report["failures"]))
    a.output.mkdir(parents=True, exist_ok=True)
    csvpath = a.output / "guardian_v3_explanations.csv"
    with csvpath.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    report["input_archive_sha256"] = sha256(a.source.read_bytes()).hexdigest()
    report["output_csv_sha256"] = sha256(csvpath.read_bytes()).hexdigest()
    report["checkpoints_in_requested_run"] = len(docs)
    report["model_sha256s_in_archive"] = sorted({d["model_sha256"] for d in docs})
    rpath = a.output / "guardian_v3_explanation_verification.json"
    rpath.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS: {len(rows)} evidence-grounded explanations from {len(docs)} checkpoint(s)")
    print(f"Source distribution: {report['explanation_source_counts']}")
    print(f"Saved: {csvpath}\nSaved: {rpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
