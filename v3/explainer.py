"""On-demand, evidence-bounded Granite explanation service for Golden HOUR V3.

No raw banking integration. Only observed, decision-time evidence may be submitted.
The returned text is a draft: heuristic validation cannot certify factual truth.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from time import perf_counter
from typing import Callable, Optional

DEFAULT_MODEL = "/home/ibm-user/granite-4.0-h-350m-base-be.f16.gguf"
NUMBER = re.compile(r"(?<![A-Za-z_])\d[\d,]*(?:\.\d+)?(?![A-Za-z_])")
ACCOUNT = re.compile(r"\bA_[A-Za-z0-9]+\b")
REJECT_PHRASES = re.compile(
    r"\b(confirmed laundering|definitely criminal|proven guilty|money recovered|"
    r"money saved|criminal proceeds|guaranteed|automatically froze|frozen account)\b", re.I
)

def evidence_key(record: dict) -> str:
    """Cache tied to the account, as-of timestamp, and actual supplied evidence."""
    fields = {k: record.get(k) for k in ("acct", "as_of", "risk_score", "reason_facts", "evidence")}
    return sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def extract_counts(facts: str) -> dict[str, str]:
    patterns = {
        "historical": r"(\d+) historical transfers",
        "counterparties": r"(\d+) counterparties",
        "cross_bank": r"(\d+) cross-bank transfers",
        "incoming": r"received (\d+) transfers?",
        "outgoing": r"sent (\d+) transfers?",
    }
    result = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, facts, re.I)
        if match:
            result[name] = match.group(1)
    return result


def factual_template(record: dict) -> str:
    acct, facts = str(record["acct"]), str(record.get("reason_facts", ""))
    counts = extract_counts(facts)
    pieces = []
    if "historical" in counts:
        pieces.append(f"{counts['historical']} observed historical transfers")
    if "counterparties" in counts:
        pieces.append(f"{counts['counterparties']} counterparties")
    if "cross_bank" in counts:
        pieces.append(f"{counts['cross_bank']} cross-bank transfers")
    if "incoming" in counts:
        pieces.append(f"{counts['incoming']} incoming transfers")
    if "outgoing" in counts:
        pieces.append(f"{counts['outgoing']} outgoing transfers")
    if pieces:
        detail = ", ".join(pieces)
    else:
        # No invented metrics. The raw evidence remains visible in the dashboard separately.
        detail = "the supplied transaction evidence"
    score = record.get("risk_score")
    score_text = f"an account-level risk score of {float(score):.3f} and " if score is not None else ""
    return (f"Account {acct} is recommended for investigator review based on {score_text}"
            f"{detail}. These indicators do not prove money laundering. "
            "Any simulated hold requires human approval.")


def validate_generated(record: dict, text: str, finish_reason: str = "stop") -> tuple[bool, str]:
    """Heuristic safety filter: rejects numerical hallucinations *and* misattached counts.

    This is not full semantic fact checking. Explanations must remain human-review drafts.
    """
    if not text or len(text) > 1100 or finish_reason == "length":
        return False, "empty, excessive or truncated generation"
    acct = str(record["acct"])
    if acct not in text or any(x != acct for x in ACCOUNT.findall(text)):
        return False, "wrong/missing account"
    if REJECT_PHRASES.search(text):
        return False, "unsupported enforcement or criminality claim"
    if "human approval" not in text.lower():
        return False, "human-approval safeguard missing"
    if "not prove money laundering" not in text.lower():
        return False, "uncertainty statement missing"
    # To prevent false 'USD recovered' implications, generated dollar claims are forbidden.
    if re.search(r"[$€£]|\bUSD\b|\bEUR\b", text, re.I):
        return False, "monetary claim in generated text"
    facts = str(record.get("reason_facts", ""))
    allowed_numbers = {x.replace(",", "") for x in NUMBER.findall(facts)}
    if record.get("risk_score") is not None:
        allowed_numbers.add(f"{float(record['risk_score']):.3f}")
    mentioned = text.replace(acct, "")
    for raw in NUMBER.findall(mentioned):
        if raw.replace(",", "") not in allowed_numbers:
            return False, f"unverified number {raw}"
    counts = extract_counts(facts)
    for label, pattern in (
        ("historical", r"(\d+) historical transfers"),
        ("counterparties", r"(\d+) counterparties"),
        ("cross_bank", r"(\d+) cross-bank transfers"),
        ("incoming", r"(?:received|incoming) (\d+) (?:incoming )?transfers?"),
        ("outgoing", r"(?:sent|outgoing) (\d+) (?:outgoing )?transfers?"),
    ):
        for m in re.finditer(pattern, mentioned, re.I):
            if label not in counts or str(int(m.group(1))) != str(int(counts[label])):
                return False, f"{label} fact association mismatch"
    return True, "heuristic checks passed; analyst review still required"


@dataclass(frozen=True)
class ExplainResult:
    text: str
    source: str  # granite or template_fallback
    note: str
    seconds: float
    key: str

    def as_dict(self) -> dict:
        return {"text": self.text, "source": self.source, "note": self.note,
                "seconds": round(self.seconds, 3), "evidence_key": self.key,
                "review_status": "AI draft — human review required"}


class GraniteExplainer:
    def __init__(self, model_path: str | None = None, max_cache: int = 64,
                 generator: Optional[Callable[[str], tuple[str, str]]] = None):
        self.model_path = Path(model_path or os.getenv("GRANITE_MODEL", DEFAULT_MODEL))
        self.max_cache = max_cache
        self.generator = generator
        self._model = None
        self._lock = Lock()  # protect llama_cpp; it is not thread-safe for concurrent generation
        self._cache: OrderedDict[str, ExplainResult] = OrderedDict()
        self.model_load_seconds: float | None = None

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Granite model not found: {self.model_path}")
        from llama_cpp import Llama  # delayed until first investigator request
        t = perf_counter()
        self._model = Llama(model_path=str(self.model_path), n_ctx=1024,
                           n_threads=int(os.getenv("GRANITE_THREADS", "2")),
                           n_gpu_layers=0, verbose=False)
        self.model_load_seconds = perf_counter() - t
        return self._model

    @staticmethod
    def _prompt(record: dict) -> str:
        # Omit estimated financial proxies. We do not know the future outcome.
        return ("Task: Restate observed evidence for an investigator. Never invent facts, amounts, "
                "time periods, or criminal conclusions. Use the exact account and numbers. "
                "Risk scores are account ranking scores, not probabilities of crime. "
                "Finish with 'These observations do not prove money laundering. "
                "Any simulated hold requires human approval.'\n\n"
                "Account: A_DEMO\nEvidence: Risk score 0.850 (account-level); 12 historical transfers; "
                "4 counterparties; 3 cross-bank transfers; HUMAN REVIEW ONLY.\n"
                "Explanation: Account A_DEMO is recommended for review based on its account-level "
                "risk score of 0.850, 12 historical transfers, 4 counterparties, and 3 cross-bank transfers. "
                "These observations do not prove money laundering. "
                "Any simulated hold requires human approval.\n\n"
                f"Account: {record['acct']}\n"
                f"Evidence: {str(record.get('reason_facts', ''))[:850]}\nExplanation:")

    def _generate(self, prompt: str) -> tuple[str, str]:
        if self.generator is not None:
            return self.generator(prompt)
        result = self._load()(prompt, max_tokens=95, temperature=0.0, top_p=0.9,
                              stop=["\n\n", "\nAccount:", "\nEvidence:"], echo=False)
        return result["choices"][0]["text"].strip(), result["choices"][0]["finish_reason"]

    def explain(self, record: dict) -> ExplainResult:
        key = evidence_key(record)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            t = perf_counter()
            try:
                text, finish = self._generate(self._prompt(record))
                ok, note = validate_generated(record, text, finish)
                source = "granite" if ok else "template_fallback"
                if not ok:
                    text = factual_template(record)
                    note = f"Generated text rejected: {note}"
            except Exception as exc:
                text = factual_template(record)
                source = "template_fallback"
                note = f"Granite unavailable ({type(exc).__name__}); using structured facts"
            output = ExplainResult(text=text, source=source, note=note,
                                   seconds=perf_counter() - t, key=key)
            self._cache[key] = output
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_cache:
                self._cache.popitem(last=False)
            return output
