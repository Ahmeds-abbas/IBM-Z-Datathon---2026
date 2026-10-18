# Golden HOUR
### Follow the money. See the connections. Make informed decisions.

**Byte Club | IBM Z Datathon 2026 | IBM LinuxONE**

**Golden HOUR** is an AI-assisted financial-crime investigation prototype. It connects suspicious transaction patterns across simulated banks, ranks accounts for investigation with **XGBoost**, prioritises limited review capacity using **Guardian** optimisation, and explains recommendations using **IBM Granite** with factual safeguards and human oversight.

> **Demo scope:** Synthetic historical financial data replayed chronologically on IBM LinuxONE. The architecture is designed to handle incoming transaction events; it is **not connected to live bank systems**, does not determine guilt and never freezes real accounts.

## The problem

Money laundering can involve transfers through many accounts and institutions. Any single bank may see only a fragment of a larger network. Meanwhile, indiscriminate restrictions can harm legitimate customers. Golden HOUR addresses both challenges: **identify connected risks and help investigators choose proportionate, time-sensitive responses**.

## How it works

```text
Pseudonymised synthetic transactions (3 simulated bank groups)
                |
     Chronological transaction replay
                |
   Time-aware account and network features
                |
         XGBoost risk ranking
                |
  Guardian constrained review prioritisation
                |
    IBM Granite grounded explanations
                |
       Human investigator review
```

1. **Data and streaming — Abdurub:** pseudonymises synthetic transactions and demonstrates chronological replay and incremental account/graph features. A separate V3 sample was selected independently of laundering labels, which remain excluded from decision-time evidence.
2. **Detection — Alex:** trains an experimental XGBoost model using **14 rolling-24-hour account features**, including transactional and cross-bank behaviour. Scores rank review priority; they are **not probabilities of criminality**.
3. **Guardian — Abdel:** considers current risk rankings, observed transaction evidence, estimated suspicious financial exposure and potential disruption to legitimate customers. It recommends **up to 10 accounts per checkpoint** for review, not automatic intervention.
4. **Explainability — Ahmed:** runs IBM Granite on recorded Guardian decision evidence. Factual validation rejects unsupported drafts and supplies conservative structured fallbacks. Explanations remain subject to human review.

## Try the working demonstration

**V3 + V2 integrated website:** [Open the HTML source](demo/golden_hour_v3_integrated_website.html). Download it and open locally in Chrome or Edge; GitHub's file preview does not run the dashboard.

- Explore **Bank views** and **Money trail** for the separate, retrospectively labelled **V2** cross-bank network demonstration.
- Open **V3 Guardian** and choose **2022-09-06 14:00 UTC**.
- Import [the ten-account V3 Granite explanation CSV](guardian_v3_outputs/guardian_v3_explanations.csv) using the website's file chooser to display the generated drafts and fallbacks.
- Expand **View evidence** to inspect the saved risk score, account facts and explanation. Review marks are local demonstration controls and do not execute holds.

**Important:** The labelled V2 network and the recorded V3 Guardian checkpoint are **different historical examples**. The V2 ring is not the evidence used to generate V3 predictions.

The separately verified retrospective V2 demo is [here](demo/golden_hour_final_v2.html).

## Verified and reported results

| Component | Evidence | Qualification |
| --- | --- | --- |
| V2 synthetic dataset | 832,742 transactions; 101,134 accounts | Retrospective, selected dataset |
| V2 XGBoost | Average precision ~0.7587; recall ~92.29% at the tested operating point | Selection bias prevents prospective accuracy claims |
| V2 historical Guardian analysis | ~$118.998M labelled laundering transaction value **touched**; ~$5.233M labelled legitimate transaction value **touched** | **Not** money frozen, saved or recovered; not a count of customers harmed or protected |
| V3 Guardian integration | **40** recorded planning checkpoints; **63** recommendation occurrences; **21** unique recommended accounts | Historical replay of synthetic data, not a bank deployment |
| V3 Granite on LinuxONE | **10/10** explanation records passed record-to-output checks; **7** Granite drafts accepted by heuristic checks and **3** safe fallbacks | Heuristic checks are not independent proof of all semantic claims |
| V3 dashboard + bridge tests | **16** dashboard tests and **6** Granite handoff tests passed in integration testing | Contract tests, not production certification |

The newer V3 detector's reported chronological average precision is approximately **1.008%**, compared with **2.492%** for a simple transaction-count baseline on that evaluation. XGBoost performed better on some fixed-budget review measures; the model remains experimental. A final labelled financial evaluation for the expanded V3 run should only be claimed if its independently checked report is included.

## IBM Z / LinuxONE proof

The team developed and tested data analysis, XGBoost inference, Guardian optimisation and IBM Granite explanation workflows on **IBM LinuxONE (s390x)**. The recorded V3 experiment connects trained risk detection to Guardian recommendations, and a later checkpoint explanation run uses a **Granite 4.0 350M GGUF** model through `llama_cpp` on LinuxONE. The investigator interface can show saved recommendations immediately rather than blocking on language-model generation.

See [V2 verification](V2_STATUS.md), [V3 release evidence](docs/V3_RELEASE_STATUS.md), and the [Granite V3 checkpoint report](guardian_v3_outputs/guardian_v3_explanation_verification.json).

## Repository map

| Location | Content |
| --- | --- |
| `demo/` | V2 and integrated V2/V3 HTML demonstrations |
| `v3/` | Investigator dashboard, recorded-demo feed, Granite explainer and tests |
| `granite_v3/` | Guardian decision → evidence-grounded explanation bridge and tests |
| `guardian_v3_outputs/` | 40-checkpoint decision archive, verified ten-account explanation CSV and report |
| `notebooks/` | IBM LinuxONE/Jupyter project notebooks |
| `docs/` | Setup, technical status and validation notes |
| `V2_STATUS.md` | Retrospective verified V2 pipeline status |

Run lightweight V3 tests from the repository root:

```bash
python3 -m unittest discover -s v3/tests -v
python3 -m unittest discover -s granite_v3/tests -v
```

These tests do not retrain models or rerun the full optimiser; those tasks require the corresponding model manifests, data and teammate source code. Large datasets, model binaries and credentials are not committed.

## Safety, social impact and limitations

Golden HOUR aims to **help investigators review potentially suspicious accounts sooner while reducing avoidable disruption to legitimate customers**. Financial benefits and social outcomes are goals, **not established real-world savings**. There is no validated count of customers protected or real funds recovered. All bank groups are simulated, and pseudonymisation does not itself prove a secure interbank information-sharing deployment.

- Historical event-time replay is **not** real-time production banking integration.
- No future laundering labels should be used for past-time scoring, Guardian selection or Granite explanations; labels are reserved for retrospective evaluation.
- Risk scores are ranking signals, not calibrated probabilities of crime or evidence of guilt.
- Guardian financial figures are estimates/proxies; historical touched value is not prevented or recovered money.
- Humans remain accountable for investigation and any real-world intervention.
- The V3 model was trained in **2026**, not actually deployed in **2022**.

## The team — Byte Club

- **Abdurub:** data preparation, privacy, replay and graph features
- **Alex:** XGBoost model and time-aware detection
- **Abdel:** Guardian optimisation and evaluation
- **Ahmed:** IBM Granite explanations and investigation interface

## Submission

- **Competition:** IBM Z Datathon 2026
- **Repository:** https://github.com/Ahmeds-abbas/IBM-Z-Datathon---2026
- **Verified V2:** [`main`](https://github.com/Ahmeds-abbas/IBM-Z-Datathon---2026/tree/main)
- **V3 demo and code:** [`v3-realtime`](https://github.com/Ahmeds-abbas/IBM-Z-Datathon---2026/tree/v3-realtime)
- **Demo video:** Add the final video URL here before publishing the README if publicly accessible.

### Open-source technologies

[IBM Granite](https://www.ibm.com/granite) · [XGBoost](https://xgboost.readthedocs.io/) · [llama.cpp](https://github.com/ggml-org/llama.cpp) · [Python](https://www.python.org/) · [scikit-learn](https://scikit-learn.org/) · [SciPy](https://scipy.org/)

See model manifests and implementation notebooks for exact model/version provenance and third-party licensing.
