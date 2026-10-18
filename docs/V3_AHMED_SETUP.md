# Golden HOUR V3 — Ahmed's Investigator Interface

A **local demo component**, not a finished live banking system. It is independent of and does not modify verified V2.

## What is implemented

- Pure Python standard-library HTTP dashboard (`v3/app.py`) with a polished, browser-based interface (`v3/dashboard.html`).
- Explicit integration API `POST /api/publish` for the snapshot, scores, and interventions produced by Abdurub, Alex, and Abdel.
- Immediate watchlist and ≤10 proposed intervention records, with **no Granite generation on the critical alert path**.
- As-of timestamp consistency, no future-dated recent transfers, no ground-truth label fields, score consistency checks, chronological checkpoints.
- Simulated investigator approve/reject actions with append-only local JSONL audit log; **no bank accounts are actually held**.
- Lazy-loaded Granite (`llama_cpp`) via a single background worker, conservative prompt, bounded LRU cache keyed by account + decision time + evidence, heuristic checks and factual template fallback.
- Mock feed to test UI and decisions before V3 state/risk/planner modules are integrated. Mock data are synthetic and not claims about live inference.

## Quick smoke test (LinuxONE or local, from the project root)

```bash
python -m unittest discover -s v3/tests -v
python -m v3.app --host 127.0.0.1 --port 8765
# In a SECOND terminal:
python -m v3.mock_feed --steps 6 --delay 1
```

Open `http://127.0.0.1:8765/` from the same machine. For remote LinuxONE/JupyterLab, use an **authenticated and correctly configured Jupyter server proxy or an SSH tunnel**; don't expose a new public port. If `jupyter-server-proxy` is already installed/configured, your authenticated Jupyter URL may provide `/proxy/8765/`; availability has not been verified. Do not guess or share Jupyter access tokens.

The mock feed makes risk rise and eventually produces a sample Guardian recommendation. Select it; risk evidence is immediate. Press **Generate Granite draft** to request on-demand explanation; approve/reject only records a simulated decision.

Granite runs only if `llama_cpp` and the model file are accessible at request time. Optional env vars: `GRANITE_MODEL` and `GRANITE_THREADS` (default 2). If unavailable or unreliable, the UI shows a **labelled template fallback** instead of inventing results. The first request may be slower because Granite is lazy-loaded.

## Real interface: publish snapshots

Expected JSON (send only the current watchlist/candidate-score slice if the entire account universe would exceed the request limit; the UI does not claim that the slice is every monitored account):

```json
{
  "snapshot": {
    "as_of": "2022-09-01T10:03:00+00:00",
    "snapshot_id": "checkpoint-3",
    "mode": "time_correct_replay",
    "total_seen": 1200,
    "recent_transactions": [
      {"tx_id":"T1","timestamp":"2022-09-01T10:02:00+00:00", "from_acct":"A_a", "to_acct":"A_b", "from_bank":"Bank_1", "to_bank":"Bank_2", "currency":"USD"}
    ],
    "bank_links": [{"from_bank":"Bank_1", "to_bank":"Bank_2", "count":12}],
    "watch_threshold":0.8
  },
  "scores": [{"acct":"A_b", "risk_score":0.94, "as_of":"2022-09-01T10:03:00+00:00", "reason_facts":"8 historical transfers; 3 counterparties; 2 cross-bank transfers"}],
  "recommendations": [{"rank":1, "acct":"A_b", "risk_score":0.94, "as_of":"2022-09-01T10:03:00+00:00", "reason_facts":"8 historical transfers; 3 counterparties; 2 cross-bank transfers", "requires_human_approval":true}]
}
```

Use `from v3.integration_adapter import publish_snapshot; publish_snapshot(snapshot, scores, recommendations)` from your integration loop. This measures UI publish round trip, **not** overall transaction-to-decision latency. If `GH_V3_INGEST_TOKEN` is set, send it in the `X-Ingest-Token` header. Keep the token outside source control. Never include `is_laundering`, future transactions, or evaluation-only labels. `risk_score` must match the score supplied by Alex for that account, and recommendation `as_of` must match the snapshot.

This is a **presentation adapter**, not an incremental graph builder, XGBoost implementation, or Guardian optimiser. Those stages must provide time-correct state. We only verify metadata/timestamp sanity on arrival; the upstream features' true point-in-time correctness still needs separate tests.

## Validation limits

The LLM factual checker catches certain numeric mismatches and prohibited phrasing but **cannot certify all semantic claims**. Granite output remains explicitly labelled for human review. For strict auditability, use structured template explanations rather than auto-approving generated prose.

Performance measurements must be taken on IBM LinuxONE with the actual V3 pipeline. Mock UI responsiveness cannot be presented as full pipeline latency.

## Files

- `v3/app.py` — live-state API, input checks, human-approval/audit service, single-worker background job
- `v3/explainer.py` — cached Granite model and validated fallback
- `v3/dashboard.html` — no build process / no external CDN
- `v3/integration_adapter.py` — `publish_snapshot()` for the replay/risk/Guardian orchestrator
- `v3/mock_feed.py` — deliberately synthetic live demo fixture
- `v3/tests/test_v3.py` — tests for timestamp isolation, labels, stale decisions, cache and factual checks
