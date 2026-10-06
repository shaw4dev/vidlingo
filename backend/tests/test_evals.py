"""Eval harness: scorers, suite runners, and the regression diff.

Everything here runs offline — the translator/gloss-provider/judge in every
test are fakes, so no test ever calls Anthropic. `main()` is exercised with
the harness's own offline demo fixture, redirected to a tmp results dir.
"""

from __future__ import annotations

import json

import pytest

from app.evals import runner
from app.evals.models import EvalCase, ScoreResult
from app.evals.scorers import (
    check_contains_any,
    check_gloss_is_chinese,
    check_gloss_matches_expected,
    check_gloss_nonempty,
    check_line_count,
    check_non_empty_lines,
    check_not_placeholder,
)

# ---- scorers ------------------------------------------------------------------

def test_check_line_count():
    assert check_line_count(["a", "b"], 2).passed
    assert not check_line_count(["a"], 2).passed


def test_check_not_placeholder_flags_leaked_marker():
    assert check_not_placeholder(["正常翻译"]).passed
    result = check_not_placeholder(["（待翻译）"])
    assert not result.passed
    assert "（待翻译）" in result.reason


def test_check_non_empty_lines_flags_blanks():
    assert check_non_empty_lines(["ok", "also ok"]).passed
    assert not check_non_empty_lines(["ok", "  "]).passed


def test_check_contains_any_scores_partial_misses():
    result = check_contains_any(["跑了", "闪电"], [["跑"], ["快"]])
    assert not result.passed
    assert result.score == 0.5  # one of two lines matched


def test_check_contains_any_skips_lines_with_no_expected_substrings():
    # an empty accepted-list for a line means "no unambiguous answer" (see t06)
    assert check_contains_any(["anything"], [[]]).passed


def test_check_gloss_matches_expected():
    assert check_gloss_matches_expected("跑, 奔跑", ["跑"]).passed
    assert not check_gloss_matches_expected("河马", ["银行", "岸"]).passed


def test_check_gloss_nonempty_and_is_chinese():
    assert check_gloss_nonempty("跑").passed
    assert not check_gloss_nonempty(None).passed
    assert check_gloss_is_chinese("跑").passed
    assert not check_gloss_is_chinese("run").passed


# ---- fakes for the suite runners ----------------------------------------------

class FakeTranslator:
    def __init__(self, replies: dict[str, str]):
        self.replies = replies

    def translate(self, texts: list[str]) -> list[str]:
        return [self.replies[t] for t in texts]


class BoomTranslator:
    def translate(self, texts: list[str]) -> list[str]:  # noqa: ARG002
        raise RuntimeError("boom: refused")


class FakeJudge:
    def __init__(self, score: int = 5):
        self.score = score
        self.calls: list[tuple] = []

    def judge_translation(self, source, candidate, reference) -> ScoreResult:
        self.calls.append((source, candidate, reference))
        return ScoreResult(passed=self.score >= 4, score=self.score / 5, reason="fake judge")


class FakeGlossProvider:
    def __init__(self, replies: dict[str, str]):
        self.replies = replies

    def gloss(self, word: str, senses) -> str | None:  # noqa: ARG002
        return self.replies.get(word)


# ---- run_translation_suite -----------------------------------------------------

def _case(id_, source, reference, accepted=None) -> EvalCase:
    expected = {"reference": reference}
    if accepted is not None:
        expected["accepted_substrings"] = accepted
    return EvalCase(id=id_, category="test", input={"source": source}, expected=expected)


def test_run_translation_suite_scores_a_good_translation():
    case = _case("t1", ["I'm going to the store."], ["我要去商店。"], accepted=[["商店"]])
    translator = FakeTranslator({"I'm going to the store.": "我要去商店。"})

    report = runner.run_translation_suite([case], translator, model="fake")

    assert report.mean_score == 1.0
    assert report.results[0].passed


def test_run_translation_suite_catches_a_bad_translation():
    case = _case(
        "t1", ["It's raining cats and dogs."], ["外面下着倾盆大雨。"], accepted=[["大雨"]]
    )
    translator = FakeTranslator({"It's raining cats and dogs.": "外面下着猫和狗。"})

    report = runner.run_translation_suite([case], translator, model="fake")

    result = report.results[0]
    assert not result.passed
    assert not result.scores["contains_expected"].passed


def test_run_translation_suite_records_subject_errors_without_crashing():
    case = _case("t1", ["hi"], ["嗨"])
    report = runner.run_translation_suite([case], BoomTranslator(), model="fake")

    result = report.results[0]
    assert result.error == "boom: refused"
    assert result.overall == 0.0
    assert not result.passed


def test_run_translation_suite_invokes_the_judge_when_given_one():
    case = _case("t1", ["hi"], ["嗨"])
    translator = FakeTranslator({"hi": "嗨"})
    judge = FakeJudge(score=5)

    report = runner.run_translation_suite([case], translator, judge=judge, model="fake")

    assert judge.calls == [(["hi"], ["嗨"], ["嗨"])]
    assert "llm_judge" in report.results[0].scores


# ---- run_gloss_suite ------------------------------------------------------------

def test_run_gloss_suite_scores_and_catches_a_bad_gloss():
    run_senses = [{"pos": "verb", "definition": "move fast"}]
    good = EvalCase(
        id="g1", category="test", input={"word": "run", "senses": run_senses},
        expected={"accepted_substrings": ["跑"]},
    )
    bank_senses = [{"pos": "noun", "definition": "a financial institution"}]
    bad = EvalCase(
        id="g2", category="test", input={"word": "bank", "senses": bank_senses},
        expected={"accepted_substrings": ["银行", "岸"]},
    )
    provider = FakeGlossProvider({"run": "跑", "bank": "河马"})

    report = runner.run_gloss_suite([good, bad], provider, model="fake")

    assert report.results[0].passed
    assert not report.results[1].passed
    assert not report.results[1].scores["matches_expected"].passed


# ---- regression diff ------------------------------------------------------------

def _result(
    case_id: str, score: float, *, passed: bool = True, reason: str = ""
) -> runner.EvalResult:
    return runner.EvalResult(
        case_id=case_id, category="c", output="x", scores={"s": ScoreResult(passed, score, reason)}
    )


def test_diff_reports_flags_a_score_drop_past_the_epsilon():
    previous = runner.EvalReport(
        suite="translation", model="m", ran_at="t0",
        results=[_result("t1", 1.0)],
    )
    current = runner.EvalReport(
        suite="translation", model="m", ran_at="t1",
        results=[_result("t1", 0.5, passed=False)],
    )

    regressions = runner.diff_reports(previous, current)

    assert len(regressions) == 1
    assert regressions[0].case_id == "t1"
    assert regressions[0].previous_score == 1.0
    assert regressions[0].current_score == 0.5


def test_diff_reports_ignores_noise_within_epsilon():
    def make(score: float) -> runner.EvalReport:
        return runner.EvalReport(
            suite="translation", model="m", ran_at="t", results=[_result("t1", score)]
        )

    regressions = runner.diff_reports(make(1.0), make(0.98))
    assert regressions == []


def test_diff_reports_with_no_previous_run_is_empty():
    current = runner.EvalReport(suite="translation", model="m", ran_at="t", results=[])
    assert runner.diff_reports(None, current) == []


# ---- report round-trip + golden datasets ------------------------------------------

def test_eval_report_to_dict_and_back_round_trips():
    report = runner.EvalReport(
        suite="translation", model="m", ran_at="t0",
        results=[_result("t1", 1.0, reason="ok")],
    )
    restored = runner.EvalReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert restored.mean_score == report.mean_score
    assert restored.results[0].scores["s"].reason == "ok"


@pytest.mark.parametrize("suite", ["translation", "gloss"])
def test_golden_datasets_load_and_are_non_empty(suite):
    cases = runner.load_cases(runner.DATASET_DIR / f"{suite}_golden.jsonl")
    assert len(cases) >= 5
    assert all(isinstance(c, EvalCase) for c in cases)


# ---- CLI end-to-end, offline demo fixture ------------------------------------------

@pytest.mark.parametrize("suite", ["translation", "gloss"])
def test_main_runs_the_offline_demo_end_to_end(monkeypatch, tmp_path, suite):
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path)

    # min-score 0: the demo fixture is deliberately imperfect, this just checks it runs end to end
    exit_code = runner.main([suite, "--min-score", "0"])

    assert exit_code == 0
    saved = list(tmp_path.glob(f"{suite}-*.json"))
    assert len(saved) == 1


def test_main_exits_nonzero_when_mean_score_is_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path)

    # 0.99 is unreachable for the deliberately-imperfect demo fixture
    exit_code = runner.main(["translation", "--min-score", "0.99"])

    assert exit_code == 1
