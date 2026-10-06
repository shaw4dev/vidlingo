"""Eval harness for the pipeline's LLM calls.

    python -m app.evals.runner translation              # offline demo fixture, no key needed
    python -m app.evals.runner translation --live        # real ANTHROPIC_API_KEY call + LLM judge
    python -m app.evals.runner gloss --live --model claude-opus-5

What this is for: `LLMTranslator` (app.pipeline.nlp) and `ClaudeGlossProvider`
(app.content.dictionary) are the two LLM calls on the content pipeline's
critical path, and until now the only way to know whether a prompt or model
change made them better or worse was to read the output by eye. This harness
runs each one against a small hand-checked golden set (`datasets/*.jsonl`),
scores the output with rule-based checks plus an LLM-as-judge, and — the
actual point of a *regression* harness — diffs the result against the
previous run so a drop shows up as a failure, not just a lower number nobody
compared to anything.

With no `--live`, the suite runs against a tiny hardcoded demo fixture instead
of the real model: free, instant, no API key, and deliberately wrong on a few
idiom/slang cases so a first run demonstrates the harness catching something
rather than reporting a suspicious all-green report. `--live` is what you'd
actually run before shipping a prompt or model change.

Exit code: 0 if the mean score clears `--min-score` and nothing regressed
vs. the previous run of the same suite, 1 otherwise — wire this into CI on
changes to nlp.py / dictionary.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.evals.models import EvalCase, EvalReport, EvalResult
from app.evals.scorers import (
    AnthropicJudge,
    Judge,
    check_contains_any,
    check_gloss_is_chinese,
    check_gloss_matches_expected,
    check_gloss_nonempty,
    check_line_count,
    check_non_empty_lines,
    check_not_placeholder,
)

DATASET_DIR = Path(__file__).parent / "datasets"
RESULTS_DIR = Path(__file__).parent / "results"

# A regression only counts once it's bigger than judge/scoring noise, so a
# 1-point flicker in an LLM-judge score doesn't fail CI on nothing.
_REGRESSION_EPSILON = 0.05


# ---- dataset loading ---------------------------------------------------------

def load_cases(path: Path) -> list[EvalCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(EvalCase(**json.loads(line)))
    return cases


# ---- running suites -----------------------------------------------------------

def run_translation_suite(
    cases: list[EvalCase], translator, judge: Judge | None = None, *, model: str = ""
) -> EvalReport:
    results = []
    for case in cases:
        source = case.input["source"]
        try:
            output = translator.translate(source)
        except Exception as exc:  # noqa: BLE001 — a subject failure is a result, not a crash
            results.append(
                EvalResult(case_id=case.id, category=case.category, output=None, error=str(exc))
            )
            continue

        scores = {
            "line_count": check_line_count(output, len(source)),
            "not_placeholder": check_not_placeholder(output),
            "non_empty": check_non_empty_lines(output),
        }
        accepted = case.expected.get("accepted_substrings")
        if accepted:
            scores["contains_expected"] = check_contains_any(output, accepted)
        if judge is not None:
            reference = case.expected.get("reference", [])
            scores["llm_judge"] = judge.judge_translation(source, output, reference)

        results.append(
            EvalResult(case_id=case.id, category=case.category, output=output, scores=scores)
        )
    return EvalReport(suite="translation", model=model, ran_at=_now(), results=results)


def run_gloss_suite(cases: list[EvalCase], gloss_provider, *, model: str = "") -> EvalReport:
    from app.content.dictionary import (
        Sense,  # noqa: PLC0415 — avoids a hard import for the translation-only path
    )

    results = []
    for case in cases:
        word = case.input["word"]
        senses = [Sense(pos=s.get("pos"), definition=s["definition"]) for s in case.input["senses"]]
        try:
            output = gloss_provider.gloss(word, senses)
        except Exception as exc:  # noqa: BLE001
            results.append(
                EvalResult(case_id=case.id, category=case.category, output=None, error=str(exc))
            )
            continue

        accepted = case.expected.get("accepted_substrings", [])
        scores = {
            "nonempty": check_gloss_nonempty(output),
            "is_chinese": check_gloss_is_chinese(output),
            "matches_expected": check_gloss_matches_expected(output, accepted),
        }
        results.append(
            EvalResult(case_id=case.id, category=case.category, output=output, scores=scores)
        )
    return EvalReport(suite="gloss", model=model, ran_at=_now(), results=results)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---- persistence + regression diff --------------------------------------------

def save_report(report: EvalReport) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = report.ran_at.replace(":", "").replace("-", "")
    path = RESULTS_DIR / f"{report.suite}-{stamp}.json"
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def latest_previous_report(suite: str) -> EvalReport | None:
    candidates = sorted(RESULTS_DIR.glob(f"{suite}-*.json"))
    if not candidates:
        return None
    return EvalReport.from_dict(json.loads(candidates[-1].read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Regression:
    case_id: str
    previous_score: float
    current_score: float


def diff_reports(previous: EvalReport | None, current: EvalReport) -> list[Regression]:
    if previous is None:
        return []
    prev_by_id = {r.case_id: r.overall for r in previous.results}
    regressions = []
    for r in current.results:
        prev_score = prev_by_id.get(r.case_id)
        if prev_score is not None and r.overall < prev_score - _REGRESSION_EPSILON:
            regressions.append(Regression(r.case_id, prev_score, r.overall))
    return regressions


# ---- offline demo fixtures ------------------------------------------------
# Not a translator or gloss provider worth trusting — a tiny lookup table over
# this repo's own golden set, wrong on purpose for the idiom/slang/phrasal
# cases, so `python -m app.evals.runner translation` (no --live, no API key)
# still exercises the whole harness and shows it catching real problems.

class _DemoTranslator:
    _KNOWN = {
        "I'm going to the store.": "我要去商店。",
        "What time is it?": "现在几点了？",
        "It's raining cats and dogs out there.": "外面下着猫和狗。",  # wrong: literal idiom
        "Break a leg tonight!": "今晚打断一条腿！",  # wrong: literal idiom
        "Get out.": "滚。",
        "I mean it, get out of my house right now.": "我是认真的，马上从我家滚出去。",
        "That's sick.": "那是有病的。",  # wrong: literal slang
        "Look at that skateboard trick, that's sick!": "看那个滑板技巧，那真是有病！",  # wrong
        "This party is lit.": "这个派对被点燃了。",  # wrong: literal slang
    }

    def translate(self, texts: list[str]) -> list[str]:
        return [self._KNOWN.get(t, "（demo fixture 没有这一句）") for t in texts]


class _DemoGlossProvider:
    _KNOWN = {
        "run": "跑",
        "book": "书",
        "bank": "河马",  # wrong: nonsense, demonstrates a caught failure
        "light": "重",  # wrong: opposite meaning
        "give up": "给上",  # wrong: word-by-word non-gloss, the failure mode the notes warn about
        "serendipity": "意外发现的美好",
    }

    def gloss(self, word: str, senses) -> str | None:  # noqa: ARG002
        return self._KNOWN.get(word)


def _build_translator(live: bool, model: str | None):
    if not live:
        return _DemoTranslator()
    from app.pipeline.nlp import LLMTranslator  # noqa: PLC0415

    return LLMTranslator(model=model) if model else LLMTranslator()


def _build_gloss_provider(live: bool, model: str | None):
    if not live:
        return _DemoGlossProvider()
    from app.content.dictionary import ClaudeGlossProvider  # noqa: PLC0415

    return ClaudeGlossProvider(model=model) if model else ClaudeGlossProvider()


# ---- CLI ---------------------------------------------------------------------

def _print_report(
    report: EvalReport, previous: EvalReport | None, regressions: list[Regression], path: Path
) -> None:
    prev_by_id = {r.case_id: r.overall for r in previous.results} if previous else {}
    print(f"\n{report.suite} eval - model={report.model or 'demo'}  ran_at={report.ran_at}")
    print(f"{'case':<6}{'category':<18}{'score':>7}{'delta':>8}  status")
    for r in report.results:
        delta = f"{r.overall - prev_by_id[r.case_id]:+.2f}" if r.case_id in prev_by_id else ""
        status = f"ERROR: {r.error}" if r.error else ("pass" if r.passed else "FAIL")
        print(f"{r.case_id:<6}{r.category:<18}{r.overall:>7.2f}{delta:>8}  {status}")

    n_fail, n_total = len(report.failures), len(report.results)
    print(f"\nmean score: {report.mean_score:.2f}  ({n_fail}/{n_total} failing)")
    if regressions:
        print("regressions vs previous run:")
        for reg in regressions:
            print(f"  {reg.case_id}: {reg.previous_score:.2f} -> {reg.current_score:.2f}")
    print(f"report saved to {path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.evals.runner")
    parser.add_argument("suite", choices=["translation", "gloss"])
    parser.add_argument(
        "--live", action="store_true", help="call the real API instead of the offline demo fixture"
    )
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--no-judge", action="store_true", help="skip the LLM-as-judge scorer (translation, --live)"
    )
    parser.add_argument(
        "--min-score", type=float, default=0.7, help="exit 1 if the mean score drops below this"
    )
    args = parser.parse_args(argv)

    cases = load_cases(DATASET_DIR / f"{args.suite}_golden.jsonl")

    if args.suite == "translation":
        translator = _build_translator(args.live, args.model)
        judge = AnthropicJudge(model=args.model) if (args.live and not args.no_judge) else None
        report = run_translation_suite(
            cases, translator, judge=judge, model=getattr(translator, "model", "demo")
        )
    else:
        gloss_provider = _build_gloss_provider(args.live, args.model)
        model_name = getattr(gloss_provider, "model", "demo")
        report = run_gloss_suite(cases, gloss_provider, model=model_name)

    previous = latest_previous_report(args.suite)
    regressions = diff_reports(previous, report)
    path = save_report(report)
    _print_report(report, previous, regressions, path)

    if report.mean_score < args.min_score:
        print(f"\nFAIL  mean score {report.mean_score:.2f} below --min-score {args.min_score}")
        return 1
    if regressions:
        print(f"\nFAIL  {len(regressions)} case(s) regressed vs the previous run")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
