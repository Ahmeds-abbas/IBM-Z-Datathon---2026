# Golden HOUR V3 — Ahmed's Granite decision handoff

## What is verified in this handoff

- Checked the uploaded `Guardian_V3_40_Checkpoint_Results_For_Abdel.zip` (40 checkpoint JSON records).
- Found **63 recommendation occurrences**, including **21 distinct account IDs**, over 40 decision checkpoints.
- Confirmed the internal Guardian decision list matches the archive's exported recommendations; each rank, decision time, account, risk score, model SHA256, supporting counts, approval requirement, and NOT_EXECUTED status passed structural checks.
- Produced **63 deterministic investigator explanations** grounded in the recorded decisions. They are **NOT Granite-generated**; source column is `structured_template_no_llm`.
- Generated a **10-account demonstration batch** for September 6, 2022 at 14:00 UTC, and a machine-readable PASS report.

This does **not** independently prove the earlier XGBoost training/evaluation, Guardian optimum, financial outcomes, or a banking deployment. The data are synthetic historical replay, and the model was trained in 2026. No laundering ground-truth labels are used in explanations.

## Output files in this ZIP

- `full_structured/guardian_v3_explanations.csv`: 63 grounded records across all 40 checkpoints.
- `full_structured/guardian_v3_explanation_verification.json`: associated validation report.
- `demo_checkpoint/guardian_v3_explanations.csv`: 10 selected records at 2022-09-06T14:00:00Z.
- `demo_checkpoint/guardian_v3_explanation_verification.json`: checkpoint-specific report.
- `granite_v3_from_guardian.py`: standalone Python 3 bridge with optional calls to Ahmed's tested `v3/explainer.py`.
- `tests/test_handoff.py`: integrity and negative-path unit tests.

Each output row includes `acct`, `decision_time`, `decision_sha256`, score, original `reason_facts`, approximate Guardian financial proxy fields, `investigator_explanation`, `granite_draft` (blank unless Granite is requested), and explicit `explanation_source`.

## Step 1 — Test the decision-to-explanation bridge on LinuxONE (NO GRANITE)

Upload this package and the original Guardian archive to `/home/ibm-user/shared` and extract the new package to a separate folder. For example:

```bash
cd /home/ibm-user/shared
unzip golden_hour_v3_granite_handoff.zip -d golden_hour_v3_granite_handoff
cd golden_hour_v3_granite_handoff
python3 -m unittest discover -s tests -v
python3 granite_v3_from_guardian.py \
  --source /home/ibm-user/shared/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip \
  --checkpoint 2022-09-06T14:00:00Z \
  --output /home/ibm-user/shared/granite_v3_checkpoint_demo
```

Expected: `PASS: 10 evidence-grounded explanations from 1 checkpoint(s)`.

## Step 2 — Run ONE real Granite generation on LinuxONE (only when RAM permits)

This script **reuses Ahmed's previously tested V3 explainer**. It does not load the model in the critical decision path, and it never modifies V2.

```bash
python3 granite_v3_from_guardian.py \
  --source /home/ibm-user/shared/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip \
  --checkpoint 2022-09-06T14:00:00Z \
  --limit 1 \
  --granite \
  --explainer-file /home/ibm-user/golden-hour-v3-ahmed-test/v3/explainer.py \
  --model-path /home/ibm-user/granite-4.0-h-350m-base-be.f16.gguf \
  --output /home/ibm-user/shared/granite_v3_one_real_inference
```

Inspect the `explanation_source`, `granite_draft`, `granite_validation_note` and `granite_seconds` columns in the output CSV. The source will be `granite_heuristic_pass_human_review_required` **only if the local GGUF model actually generated text that passed the heuristic validator**. Otherwise it is `granite_rejected_or_unavailable_structured_fallback`, and the note explains why. The grounded `investigator_explanation` remains safe and labelled as deterministic.

**RAM caution:** Previous shared LinuxONE availability was around 1.6 GiB, with several large Jupyter kernels. Before inference, coordinate with the team to shut down their own idle kernels. The ~653MB GGUF can require substantially more RAM during loading/inference; avoid running Granite concurrently with Guardian if memory is low. No need to train or rerun XGBoost.

If the first live Granite call succeeds, remove `--limit 1` to run Granite for the chosen checkpoint (10 separate record versions). The 63-row structured CSV already exists, so **don't run all 63 Granite generations by default**; that can take many minutes.

## Verification rules

- **Identity:** Each (checkpoint time, account) must exist exactly once in the corresponding Guardian decision.
- **Time:** `feature_cutoff`, `score_available_at` and evidence window must not be in the future relative to the decision.
- **Evidence:** The score, historical transfer counts, counterparts, cross-bank counts and USD proxies are taken from that exact decision JSON; the code checks key values before writing.
- **Execution:** All records must be `ACCOUNT_REVIEW_RECOMMENDATION`, `NOT_EXECUTED`, `requires_human_approval=true`.
- **Granite:** Generated drafts are subjected to Ahmed's existing heuristic validator and are **still subject to human fact review**. The structured investigator explanation is not falsely labelled as model-generated.
- **Financial language:** `est_money_blocked` is a *capped suspicion proxy*, not actual funds blocked/recovered. `estimated_proxy_collateral` is uncalibrated and is not verified actual customer loss.

The output CSV is **not** an independently validated economic result and does not prove that an intervention was effective.

## Never overwrite V2

These scripts write only to a new `--output` folder. They do not edit the original transaction dataset, model, `guardian_v2_outputs`, or `freeze_plan.csv`.
