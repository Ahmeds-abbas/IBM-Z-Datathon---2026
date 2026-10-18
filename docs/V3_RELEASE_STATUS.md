# Golden HOUR V3 — Recorded Decision Demonstration

**Byte Club | IBM Z Datathon 2026 | IBM LinuxONE (s390x)**

## What is demonstrated

- Synthetic transaction data replayed in historical event-time; no real bank feed or actual account freeze.
- Teammates reported an integrated time-aware XGBoost risk scorer and Guardian V3 optimisation across **40 decision checkpoints** (63 recommendation occurrences, 21 distinct accounts). The decision archive is included for inspection. Original training/optimiser metrics should be checked against their dedicated source notebooks and audit reports.
- The 2022-09-06 14:00 UTC checkpoint contains ten recorded recommendations. Ahmed generated ten explanation records on LinuxONE using a Granite 4.0 350M GGUF model: **7 draft explanations passed heuristic validation and 3 received conservative structured fallbacks**. All 10 passed record-to-output verification. Heuristic checks cannot certify full semantic correctness; all outputs require analyst review.
- The self-contained website integrates the V2 money-trail example and a separate recorded V3 Guardian console. Its V3 UI **imports** the ten-account Granite CSV from the file chooser; it does not run the model in the browser.

## Demo entry point

Open `demo/golden_hour_v3_integrated_website.html` locally in a browser. Go to the **V3 Guardian** section, choose checkpoint `2022-09-06T14:00:00Z`, then import `guardian_v3_outputs/guardian_v3_explanations.csv` to show the seven Granite-accepted drafts and three structured fallbacks.

The V2 network ring shown elsewhere in the website is a **separate retrospectively labelled example**. Do not present its edges as the V3 checkpoint's decision-time evidence.

## Source and evidence

- `v3/` — investigator dashboard, replay presentation adapter, lazy Granite explainer and unit tests.
- `granite_v3/` — decision-to-explanation bridge, tests, and its own README.
- `guardian_v3_outputs/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip` — 40 recorded Guardian decisions. No laundering ground truth is included in Granite explanations.
- `guardian_v3_outputs/guardian_v3_explanations.csv` — **copy the real LinuxONE Granite-generated checkpoint output into this path** (not included in the staging ZIP).
- `guardian_v3_outputs/guardian_v3_explanation_verification.json` — real PASS report from the same run (not included in the staging ZIP).

### Verified Granite checkpoint output provenance

- Historical checkpoint: **2022-09-06T14:00:00Z**.
- Granite run: 10 recommendations; **7 heuristic-accepted drafts, 3 fallback explanations**.
- Verification: `status=PASS`, `failures=[]`, `granite_model_generation_confirmed=true`, ten explained accounts.
- Reported CSV SHA-256: `6abec7a5b374e558ce9102103a71374b64e61e06c49434f0e5c436f5f1efd378`.
- Input archive SHA-256: `8f5f2473c556a92e74062cac7bd8339eaaf0f6fc34e1e9de0aafc1ba97c68253`.

## Important limitations

- Financial proxies are **not recovered funds or proven laundering amounts**; ground truth is reserved for separate retrospective evaluation.
- XGBoost was trained in 2026, not deployed in 2022. No live-banking feed or live holds.
- Model scores are **risk ranking signals**, not calibrated probabilities of criminality. The low V3 average precision and imperfect comparison to the transaction-count baseline must not be hidden in technical disclosures.
- The website and recorded console are presentation outputs, **not** evidence of continuous end-to-end bank integration.
- No secrets, PAT tokens, raw sensitive datasets, GGUF weights, notebook checkpoints, or large model artifacts should be committed.
