"""LessonPackage validation: JSON Schema (structure) + semantic invariants.

The schema catches shape errors; `_semantic_errors` catches cross-field rules a
JSON Schema cannot express (token spans landing inside the text, sentences being
ordered and non-overlapping, index rows referencing real sentences/tokens).

A package is valid iff `validate_package` returns an empty list.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "schema" / "lesson_package.schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_errors(data: Any) -> list[str]:
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    out = []
    for e in errors:
        loc = "/".join(str(p) for p in e.path) or "<root>"
        out.append(f"schema: {loc}: {e.message}")
    return out


def _semantic_errors(data: dict) -> list[str]:
    errors: list[str] = []
    video = data["video"]
    duration = video["duration_ms"]
    sentences = data["sentences"]

    seen_ids: set[str] = set()
    seen_idx: set[int] = set()
    prev_end = -1
    for s in sentences:
        sid = s["id"]
        where = f"sentence[{s.get('idx')}] id={sid!r}"

        if sid in seen_ids:
            errors.append(f"{where}: duplicate sentence id")
        seen_ids.add(sid)
        if s["idx"] in seen_idx:
            errors.append(f"{where}: duplicate idx")
        seen_idx.add(s["idx"])

        if s["start_ms"] >= s["end_ms"]:
            errors.append(f"{where}: start_ms ({s['start_ms']}) must be < end_ms ({s['end_ms']})")
        if s["end_ms"] > duration:
            errors.append(f"{where}: end_ms ({s['end_ms']}) exceeds video duration ({duration})")
        if s["start_ms"] < prev_end:
            errors.append(
                f"{where}: overlaps previous sentence (starts before prior end {prev_end})"
            )
        prev_end = max(prev_end, s["end_ms"])

        text = s["text_en"]
        for t in s["tokens"]:
            start, end = t["char_span"]
            tw = f"{where} token {t.get('surface')!r}"
            if start >= end:
                errors.append(f"{tw}: char_span start ({start}) must be < end ({end})")
                continue
            if end > len(text):
                errors.append(f"{tw}: char_span end ({end}) exceeds text_en length ({len(text)})")
                continue
            if text[start:end] != t["surface"]:
                errors.append(
                    f"{tw}: surface does not match text_en[{start}:{end}]={text[start:end]!r}"
                )

    # idx should be a contiguous 0..n-1 sequence (the pipeline emits them in order).
    if seen_idx and seen_idx != set(range(len(sentences))):
        errors.append(f"sentences: idx values must be contiguous 0..{len(sentences) - 1}")

    for i, row in enumerate(data.get("index", [])):
        if row["sentence_id"] not in seen_ids:
            errors.append(f"index[{i}]: references unknown sentence_id {row['sentence_id']!r}")

    return errors


def validate_package(data: Any) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    schema_errs = _schema_errors(data)
    if schema_errs:
        # Skip semantic checks when structure is wrong (would raise KeyError).
        return schema_errs
    return _semantic_errors(data)


def validate_file(path: str | Path) -> list[str]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return [f"file: cannot read {path}: {e}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"json: {e}"]
    return validate_package(data)
