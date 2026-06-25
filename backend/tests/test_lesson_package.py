import json
from pathlib import Path

from app.content.validator import validate_file, validate_package

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = BACKEND / "samples" / "lesson_package.sample.json"
FIXTURES = Path(__file__).parent / "fixtures"


def test_sample_package_is_valid():
    assert validate_file(SAMPLE) == []


def test_invalid_schema_is_rejected():
    errors = validate_file(FIXTURES / "lesson_package.invalid_schema.json")
    assert errors, "expected schema errors"
    assert all(e.startswith("schema:") for e in errors)
    # bad license enum and bad difficulty enum should both be reported
    blob = "\n".join(errors)
    assert "license_tag" in blob
    assert "difficulty" in blob


def test_invalid_semantic_is_rejected():
    errors = validate_file(FIXTURES / "lesson_package.invalid_semantic.json")
    assert errors, "expected semantic errors"
    blob = "\n".join(errors)
    assert "exceeds video duration" in blob
    assert "surface does not match" in blob
    assert "exceeds text_en length" in blob
    assert "unknown sentence_id" in blob


def test_malformed_json_is_rejected():
    errors = validate_file(FIXTURES / "lesson_package.malformed.json")
    assert errors and errors[0].startswith("json:")


def test_missing_file_is_rejected():
    errors = validate_file(FIXTURES / "does_not_exist.json")
    assert errors and errors[0].startswith("file:")  # no crash


def test_youtube_provider_requires_youtube_id():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    del data["video"]["youtube_id"]
    errors = validate_package(data)
    assert any("youtube_id" in e for e in errors)


def test_bad_youtube_id_pattern_rejected():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    data["video"]["youtube_id"] = "too-short"
    errors = validate_package(data)
    assert any("youtube_id" in e for e in errors)


def test_overlap_and_idx_gaps_detected():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    # make sentence 2 overlap sentence 1 and break idx contiguity
    data["sentences"][1]["start_ms"] = 1000
    data["sentences"][1]["idx"] = 5
    errors = validate_package(data)
    blob = "\n".join(errors)
    assert "overlaps previous sentence" in blob
    assert "contiguous" in blob
