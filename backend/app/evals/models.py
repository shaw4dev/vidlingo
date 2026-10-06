"""Shared types for the eval harness.

An `EvalCase` is one golden example — an input plus whatever a scorer needs to
judge the output against it. An `EvalResult` is one case after it has been run
through a subject (an `LLMTranslator`, a `ClaudeGlossProvider`, ...) and scored.
An `EvalReport` is a full suite run: every result, plus the aggregate numbers
`runner.py` uses to detect regressions against the previous run.

Frozen where a value shouldn't change after construction (a case is data you
loaded from disk; a score is a fact about one run), plain dataclasses for the
report, which `runner.py` builds up incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """One golden example. `input`/`expected` are subject-specific dicts rather
    than a fixed schema, since a translation case and a gloss case need
    different fields — the scorer for each suite knows how to read its own."""

    id: str
    category: str
    input: dict
    expected: dict
    notes: str = ""


@dataclass(frozen=True)
class ScoreResult:
    """One scorer's verdict on one case. `score` is 0.0-1.0 so rule-based and
    LLM-judge scorers can be averaged together; `passed` is the pass/fail a
    report counts, kept separate from `score` because a judge score of e.g.
    0.7 might still count as a pass depending on the scorer's own threshold."""

    passed: bool
    score: float
    reason: str


@dataclass
class EvalResult:
    """One case after running + scoring. `error` is set instead of `scores`
    when the subject itself raised (a translation refusal, a malformed reply)
    — that's a hard failure, not a low score, and reported separately so it
    doesn't get averaged away."""

    case_id: str
    category: str
    output: object
    scores: dict[str, ScoreResult] = field(default_factory=dict)
    error: str | None = None

    @property
    def overall(self) -> float:
        if self.error or not self.scores:
            return 0.0
        return sum(s.score for s in self.scores.values()) / len(self.scores)

    @property
    def passed(self) -> bool:
        return self.error is None and all(s.passed for s in self.scores.values())

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "output": self.output,
            "scores": {
                name: {"passed": s.passed, "score": s.score, "reason": s.reason}
                for name, s in self.scores.items()
            },
            "error": self.error,
            "overall": self.overall,
            "passed": self.passed,
        }


@dataclass
class EvalReport:
    """A full suite run, plus everything needed to diff it against the run
    before it — that diff, not the single-run score, is the point of a
    regression harness: a 0.81 mean is meaningless on its own, but 0.81 down
    from 0.90 after a prompt change is exactly what should fail CI."""

    suite: str
    model: str
    ran_at: str
    results: list[EvalResult]

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.overall for r in self.results) / len(self.results)

    @property
    def failures(self) -> list[EvalResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "model": self.model,
            "ran_at": self.ran_at,
            "mean_score": self.mean_score,
            "results": [r.to_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data: dict) -> EvalReport:
        results = []
        for r in data["results"]:
            scores = {
                name: ScoreResult(passed=s["passed"], score=s["score"], reason=s["reason"])
                for name, s in r["scores"].items()
            }
            results.append(
                EvalResult(
                    case_id=r["case_id"],
                    category=r["category"],
                    output=r["output"],
                    scores=scores,
                    error=r["error"],
                )
            )
        return cls(suite=data["suite"], model=data["model"], ran_at=data["ran_at"], results=results)
