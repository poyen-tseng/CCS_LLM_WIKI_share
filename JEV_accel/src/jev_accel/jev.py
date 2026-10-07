"""Thin gate around the TypeSafe Jev API.

Every call is logged to results/decisions.jsonl (state, answers, latency, model, tokens) so the
calibration can be checked later. Missing key or any API failure returns a Decision with
source != "jev" and the caller keeps its L0 (rule) answer.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import RESULTS, load_config

try:  # the SDK is a hard dependency, but keep the rules usable if it is missing
    import typesafe_sdk as _ts
except ImportError:  # pragma: no cover
    _ts = None


@dataclass
class Decision:
    source: str  # "jev" | "unavailable" | "error"
    answers: dict[str, dict] = field(default_factory=dict)
    latency_ms: float | None = None
    model: str | None = None
    input_tokens: int | None = None
    error: str | None = None

    def choice(self, qid: str) -> tuple[str | None, float]:
        a = self.answers.get(qid)
        return (a["choice"], a["confidence"]) if a and a.get("type") == "choice" else (None, 0.0)

    def noul(self, qid: str) -> float | None:
        a = self.answers.get(qid)
        return a["noul"] if a and a.get("type") == "noul" else None

    def to_dict(self) -> dict:
        return asdict(self)


def _answer_dict(ans: Any) -> dict:
    d = ans.model_dump()
    if "probabilities" in d:  # Score probabilities have int keys; keep JSON-friendly
        d["probabilities"] = {str(k): round(v, 4) for k, v in d["probabilities"].items()}
    d.pop("legend", None)
    return d


class JevGate:
    def __init__(self, cfg: dict | None = None, log: bool = True):
        self.cfg = (cfg or load_config())["jev"]
        self.log = log
        self._client = None

    @property
    def available(self) -> bool:
        return _ts is not None and bool(os.environ.get("TYPESAFE_API_KEY"))

    def _get_client(self):
        if self._client is None:
            self._client = _ts.TypeSafeClient(
                model=self.cfg["model"],
                timeout=self.cfg["timeout_s"],
                retry=_ts.RetryPolicy(max_retries=self.cfg["max_retries"], timeout=self.cfg["timeout_s"] * 2),
            )
        return self._client

    def ask(self, state: dict, questions: dict, tag: str = "") -> Decision:
        if not self.available:
            return self._record(tag, state, Decision("unavailable", error="TYPESAFE_API_KEY not set"))
        t0 = time.perf_counter()
        try:
            r = self._get_client().system_one(state=state, questions=questions)
        except Exception as e:  # auth, rate limit, network: fall back to rules
            return self._record(tag, state, Decision("error", latency_ms=_ms(t0), error=f"{type(e).__name__}: {e}"))
        d = Decision(
            "jev",
            answers={k: _answer_dict(v) for k, v in r.answers.items()},
            latency_ms=_ms(t0),
            model=r.model,
            input_tokens=r.usage.input_tokens if r.usage else None,
        )
        return self._record(tag, state, d)

    def confident_choice(self, d: Decision, qid: str) -> str | None:
        label, conf = d.choice(qid)
        return label if label is not None and conf >= self.cfg["min_choice_confidence"] else None

    def confident_noul(self, d: Decision, qid: str) -> bool | None:
        p = d.noul(qid)
        if p is None:
            return None
        if p >= self.cfg["noul_yes"]:
            return True
        if p <= self.cfg["noul_no"]:
            return False
        return None

    def _record(self, tag: str, state: dict, d: Decision) -> Decision:
        if self.log:
            RESULTS.mkdir(parents=True, exist_ok=True)
            line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "state": state, **d.to_dict()}
            with open(RESULTS / "decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        return d

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)
