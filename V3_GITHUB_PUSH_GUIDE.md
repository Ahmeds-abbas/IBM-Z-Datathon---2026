# Golden HOUR V3 — Safe GitHub upload instructions

**Target:** `https://github.com/Ahmeds-abbas/IBM-Z-Datathon---2026/tree/v3-realtime`

This ZIP is a ready-to-stage *subset* of the final V3 release: the integrated website, Ahmed's dashboard/Granite code and tests, and Guardian recorded decision archive. The **real Granite output CSV and verification JSON** exist only on your LinuxONE server and must be copied separately. Teammates' latest XGBoost, streaming and Guardian *source code* should be staged by their respective owners.

### 1. Clone branch into a NEW folder in Jupyter terminal

```bash
cd /home/ibm-user/shared
git clone --branch v3-realtime --single-branch \
  https://github.com/Ahmeds-abbas/IBM-Z-Datathon---2026.git golden-hour-v3-release
```

If `golden-hour-v3-release` already exists, don't overwrite it: check its Git status and choose a different fresh folder name.

### 2. Unpack release files into the Git clone

```bash
cd /home/ibm-user/shared
unzip -o golden_hour_v3_github_release.zip -d golden-hour-v3-release
```

### 3. Copy the actual Granite inference results (DO NOT skip)

```bash
mkdir -p /home/ibm-user/shared/golden-hour-v3-release/guardian_v3_outputs
cp /home/ibm-user/shared/granite_v3_checkpoint_10_llm/guardian_v3_explanations.csv \
   /home/ibm-user/shared/golden-hour-v3-release/guardian_v3_outputs/
cp /home/ibm-user/shared/granite_v3_checkpoint_10_llm/guardian_v3_explanation_verification.json \
   /home/ibm-user/shared/golden-hour-v3-release/guardian_v3_outputs/
```

Check output fingerprints:

```bash
cd /home/ibm-user/shared/golden-hour-v3-release
sha256sum guardian_v3_outputs/guardian_v3_explanations.csv
python3 -m json.tool guardian_v3_outputs/guardian_v3_explanation_verification.json | tail -n 12
```

CSV SHA-256 must equal `6abec7a5b374e558ce9102103a71374b64e61e06c49434f0e5c436f5f1efd378` from the verified run. Recheck the report says PASS with ten records, 7 Granite drafts and 3 fallbacks.

### 4. Check source tests (no Granite load required)

```bash
python3 -m unittest discover -s v3/tests -v
python3 -m unittest discover -s granite_v3/tests -v
```

### 5. Stage just the verified files, inspect and push

```bash
git status --short
git add demo/golden_hour_v3_integrated_website.html \
  docs/V3_RELEASE_STATUS.md docs/V3_AHMED_SETUP.md docs/V3_RECORDED_DASHBOARD.md \
  v3/ granite_v3/ notebooks/golden_hour_v3_jupyter_investigator.ipynb \
  guardian_v3_outputs/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip \
  guardian_v3_outputs/guardian_v3_explanations.csv \
  guardian_v3_outputs/guardian_v3_explanation_verification.json
git diff --cached --stat
git diff --cached --name-only
git commit -m "feat(v3): publish recorded Guardian and Granite investigator demo"
git push origin v3-realtime
```

If GitHub prompts for credentials, use your normal approved Git authentication workflow or a PAT as a **password in a credential prompt only**. Never paste secrets into chat or commit them. If teammates are concurrently pushing, `git pull --rebase origin v3-realtime` **only after checking their changes**; do not force push.

### 6. Verify on GitHub

Check the `v3-realtime` branch has `demo/golden_hour_v3_integrated_website.html`, `v3/`, `granite_v3/`, and `guardian_v3_outputs/`. Verify `main` still has the preserved V2 submission. Share the `v3-realtime` branch link with the team.

The bundle does **not** contain the teammates' full latest source or model artifacts. Ask Abdurub/Alex/Abdel to add their code and audited model manifest (not large model weights or raw data) before declaring the **whole team V3 repository complete**.
