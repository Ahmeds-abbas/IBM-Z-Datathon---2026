# Golden HOUR — Recorded V3 Dashboard Bridge

This is an **additive** patch to Ahmed's original `v3.app` code. It does not
change the original mock feed, notebooks, Granite model or V2.

Purpose: load the actual Guardian checkpoint and the already generated Granite
explanation output into the existing Jupyter investigator panel and simulated
approve/reject audit controls. It does **not** rerun XGBoost, Guardian, or Granite.

## Install in the original V3 dashboard project on LinuxONE

From your `/home/ibm-user/shared/` directory, unzip this ZIP into the existing
Ahmed test project (adds only `v3/recorded_demo.py`, a regression test, and docs):

```sh
unzip golden_hour_v3_dashboard_recorded_patch.zip -d /home/ibm-user/golden-hour-v3-ahmed-test
cd /home/ibm-user/golden-hour-v3-ahmed-test
python3 -m unittest discover -s v3/tests -v
```

## Run ONE recorded checkpoint in the existing server interface

```sh
python3 -m v3.recorded_demo \
  --archive /home/ibm-user/shared/golden_hour_v3_granite_handoff/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip \
  --explanations /home/ibm-user/shared/granite_v3_checkpoint_10_llm/guardian_v3_explanations.csv \
  --checkpoint 2022-09-06T14:00:00Z \
  --host 127.0.0.1 --port 8765
```

Now reopen `shared/golden_hour_v3_jupyter_investigator.ipynb` and run its
connection check and interactive widget cell. It reads the same `/api/state`
endpoint. You should see 10 Guardian recommendations and imported explanations
for each. `Generate Granite draft` is no longer necessary: already verified
outputs are loaded, and clicking it simply returns the cached record.

The approval button creates a **new simulated human decision** in
`v3/recorded_demo_audit.jsonl`; it does not execute any real bank hold or change
the original Guardian decision JSON.

## Important display limitations

- The dashboard is in `RECORDED_GUARDIAN_V3_NOT_LIVE` mode. It is historical
  event-time replay, **not** streaming directly from a bank.
- The `Accounts scored` / `Watchlist` figures include **only** selected Guardian
  accounts and saved risk-only top-k accounts. The archive did not include the
  full original model score vector; do not describe these as whole-network totals.
- The archive does not include raw recent transaction rows or complete bank-link
  counts. Those parts of the old dashboard remain empty. **Do not populate them
  with fictional transactions.** The evidence facts show cross-bank transfer counts
  for each recommended account.
- The original `decision_id` used by the UI is an internal evidence key. The full
  `guardian_decision_sha256` is preserved on each recommendation in API state.
- Granite accepted 7/10 drafts under heuristic checks in the user's recorded run.
  The remaining 3 show conservative structured fallback text. **All** explanations
  still require human analyst review.
- The XGBoost model was built in 2026 and is replayed on 2022 synthetic data;
  there was no actual 2022 live deployment.
- Keep the server bound to localhost; do not expose port 8765 publicly.

Stop the server with Ctrl+C after the demonstration.
