"""Scorers for the two eval suites: translation (`LLMTranslator`) and gloss
(`ClaudeGlossProvider`).

Two kinds, deliberately kept separate rather than blended into one number:

  rule-based  — cheap, deterministic, zero LLM calls. Catches the failures
                that matter most in production (placeholder text leaking
                through, a blank gloss, a line-count mismatch) with no
                flakiness and no cost.
  LLM-as-judge — for "is this actually a good translation", which no regex
                can answer. Slower, costs a call, and is itself a model output
                so it can be wrong — treat its score as a strong signal, not
                ground truth, which is why it's one scorer among several
                rather than the only one.

The judge is a `Judge` Protocol, not a hardcoded Anthropic call, so
`test_evals.py` can inject a fake and run the whole harness with zero network
access — same pattern as `DictionaryProvider`/`GlossProvider` in
app.content.dictionary.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from app.evals.models import ScoreResult

_PLACEHOLDER_MARKERS = ("（待翻译）",)  # PlaceholderTranslator.marker
_HAN_RE = re.compile(r"[一-鿿]")


# ---- translation: rule-based ------------------------------------------------

def check_line_count(output: list[str], expected_count: int) -> ScoreResult:
    ok = len(output) == expected_count
    reason = "line count matches" if ok else f"got {len(output)} lines, expected {expected_count}"
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0, reason=reason)


def check_not_placeholder(output: list[str]) -> ScoreResult:
    leaked = [line for line in output if any(m in line for m in _PLACEHOLDER_MARKERS)]
    ok = not leaked
    return ScoreResult(
        passed=ok,
        score=1.0 if ok else 0.0,
        reason="no placeholder text" if ok else f"placeholder leaked into: {leaked}",
    )


def check_non_empty_lines(output: list[str]) -> ScoreResult:
    blanks = [i for i, line in enumerate(output) if not line.strip()]
    ok = not blanks
    return ScoreResult(
        passed=ok,
        score=1.0 if ok else 0.0,
        reason="no blank lines" if ok else f"blank line(s) at index {blanks}",
    )


def check_contains_any(output: list[str], accepted_substrings: list[list[str]]) -> ScoreResult:
    """Soft grounding check: for each line, at least one of its accepted
    substrings (from the golden case) should appear. Skipped (auto-pass) for
    lines whose golden case gives no substrings — not every line has an
    unambiguous "must contain X" answer."""
    misses = []
    for i, (line, accepted) in enumerate(zip(output, accepted_substrings, strict=False)):
        if accepted and not any(sub in line for sub in accepted):
            misses.append((i, accepted))
    ok = not misses
    return ScoreResult(
        passed=ok,
        score=1.0 if ok else max(0.0, 1.0 - len(misses) / max(len(output), 1)),
        reason="expected phrases present" if ok else f"missing expected phrase(s) at: {misses}",
    )


# ---- gloss: rule-based -------------------------------------------------------

def check_gloss_nonempty(gloss: str | None) -> ScoreResult:
    ok = bool(gloss and gloss.strip())
    reason = "non-empty" if ok else "empty gloss"
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0, reason=reason)


def check_gloss_is_chinese(gloss: str | None) -> ScoreResult:
    ok = bool(gloss and _HAN_RE.search(gloss))
    reason = "contains Han characters" if ok else "no Han characters found"
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0, reason=reason)


def check_gloss_matches_expected(gloss: str | None, accepted_substrings: list[str]) -> ScoreResult:
    if not accepted_substrings:
        return ScoreResult(passed=True, score=1.0, reason="no expected substrings given")
    ok = bool(gloss) and any(sub in gloss for sub in accepted_substrings)
    if ok:
        reason = "matched an accepted gloss"
    else:
        reason = f"'{gloss}' matched none of {accepted_substrings}"
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0, reason=reason)


# ---- LLM-as-judge ------------------------------------------------------------

class Judge(Protocol):
    def judge_translation(
        self, source: list[str], candidate: list[str], reference: list[str]
    ) -> ScoreResult: ...


_JUDGE_PASS_THRESHOLD = 4  # out of 5


class AnthropicJudge:
    """The real judge: one extra call per case, scoring 1-5 against a rubric.

    Kept to a single number + one-line reason rather than free-form critique —
    a report with 20 cases needs to be skimmable, and a numeric score is what
    `EvalReport.mean_score` and the regression diff actually consume.
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("EVAL_JUDGE_MODEL") or "claude-opus-5"

    def judge_translation(
        self, source: list[str], candidate: list[str], reference: list[str]
    ) -> ScoreResult:
        from anthropic import Anthropic  # noqa: PLC0415 (optional dependency, matches nlp.py)

        prompt = (
            "You are grading a Chinese subtitle translation for a Chinese-speaking "
            "English learner. Score how well CANDIDATE conveys SOURCE, using REFERENCE "
            "as one acceptable answer (not the only one — natural paraphrases are fine).\n\n"
            f"SOURCE:\n{_numbered(source)}\n\nREFERENCE:\n{_numbered(reference)}\n\n"
            f"CANDIDATE:\n{_numbered(candidate)}\n\n"
            "Reply with ONLY a JSON object: "
            '{"score": <1-5 integer>, "reason": "<one sentence>"}. '
            "5 = faithful and natural, 3 = understandable but off in places, "
            "1 = wrong or nonsensical."
        )
        msg = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
            model=self.model,
            max_tokens=300,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        try:
            parsed = json.loads(text)
            score = int(parsed["score"])
            reason = str(parsed.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # The judge itself misbehaved — surface that as a failed score
            # rather than crashing the whole suite over one bad reply.
            reason = f"judge reply unparseable: {exc} ({text[:200]!r})"
            return ScoreResult(passed=False, score=0.0, reason=reason)
        return ScoreResult(passed=score >= _JUDGE_PASS_THRESHOLD, score=score / 5, reason=reason)


def _numbered(lines: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(lines))
