"""Lightweight tokenization + lemmatization, and the Translator interface.

v0 uses regex tokenization + rule-based lemmatization: zero heavy deps, fully
deterministic, good enough to seed the word index. A proper NLP model (spaCy)
can drop in behind `tokenize`/`lemmatize` later without touching the pipeline.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

# Word = letters with optional internal apostrophe (How's, don't).
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

_IRREGULAR = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be", "being": "be",
    "has": "have", "had": "have", "having": "have",
    "does": "do", "did": "do", "done": "do", "doing": "do",
    "went": "go", "gone": "go", "going": "go", "goes": "go",
    "said": "say", "made": "make", "got": "get",
}


def lemmatize(word: str) -> str:
    """Very small rule-based lemmatizer. Heuristic, not linguistically exact."""
    w = word.lower()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    for suffix in ("ing", "ed"):
        if w.endswith(suffix) and len(w) > len(suffix) + 1:
            base = w[: -len(suffix)]
            # de-double a final consonant: running -> run
            if len(base) >= 2 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        if w.endswith("ies"):
            return w[:-3] + "y"
        if w.endswith("es"):
            return w[:-2]
        return w[:-1]
    return w


def tokenize(text: str) -> list[dict]:
    """Return tappable token spans over `text`.

    Each token: {"char_span": [start, end], "surface": str, "lemma": str}.
    char_span indexes into `text` exactly, so surfaces round-trip and pass
    LessonPackage validation.
    """
    tokens: list[dict] = []
    for m in _WORD_RE.finditer(text):
        surface = m.group()
        tokens.append(
            {
                "char_span": [m.start(), m.end()],
                "surface": surface,
                "lemma": lemmatize(surface),
            }
        )
    return tokens


class Translator(Protocol):
    def translate(self, texts: list[str]) -> list[str]:
        ...


class PlaceholderTranslator:
    """Dev default: emits a non-empty placeholder so packages validate offline.

    NOT real translation. Swap in ClaudeTranslator (below) for usable content.
    """

    marker = "（待翻译）"

    def translate(self, texts: list[str]) -> list[str]:
        return [self.marker for _ in texts]


class TranslationRefused(Exception):
    """The model's safety classifiers declined the batch. Distinct from a
    transport error: retrying the same text will be declined the same way."""


class LLMTranslator:
    """Translation via any endpoint that speaks the Anthropic Messages API.

    Defaults to Anthropic itself. Point `ANTHROPIC_BASE_URL` at a compatible
    gateway (DeepSeek's Anthropic endpoint, an aggregator) and set
    `TRANSLATE_MODEL` to that provider's model id to use it instead — the SDK
    reads the base URL from the environment on its own, so only the model name
    and one env var change.

    `anthropic` is an optional extra (`pip install -e ".[llm]"`) and imported
    lazily, so the pipeline stays dependency-light. Enable with `--translate llm`.

    Subtitles are translated in numbered batches rather than one call per line:
    a line of dialogue out of context is often untranslatable ("Get out." is a
    different sentence depending on what came before), and batching also keeps
    the call count proportional to lessons rather than sentences.
    """

    DEFAULT_MODEL = "claude-opus-5"

    def __init__(self, model: str | None = None, effort: str = "medium"):
        self.model = model or os.getenv("TRANSLATE_MODEL") or self.DEFAULT_MODEL
        self.effort = effort

    def translate(self, texts: list[str]) -> list[str]:
        from anthropic import Anthropic  # noqa: PLC0415

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        joined = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))

        extra: dict = {}
        if not os.getenv("ANTHROPIC_BASE_URL"):
            # `effort` is an Anthropic-only parameter. A third-party gateway
            # that merely speaks the Messages wire format will usually 400 on
            # an unknown field, so only send it when talking to Anthropic.
            extra["output_config"] = {"effort": self.effort}

        msg = client.messages.create(
            model=self.model,
            # On Anthropic's current models thinking is on by default and shares
            # this budget with the response, so leave real headroom or long
            # batches truncate mid-answer.
            max_tokens=8000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Translate each numbered English line into natural, "
                        "conversational Simplified Chinese. Return ONLY the "
                        "translations, one per line, same numbering.\n\n" + joined
                    ),
                }
            ],
            **extra,
        )
        if msg.stop_reason == "refusal":
            # A 200 with no usable content. Say so rather than crashing on an
            # empty content list two lines down. Providers that never emit this
            # stop reason simply never take the branch.
            raise TranslationRefused(
                getattr(getattr(msg, "stop_details", None), "category", None) or "unspecified"
            )
        text = "".join(b.text for b in msg.content if b.type == "text")
        out = text.strip().splitlines()
        cleaned = [re.sub(r"^\s*\d+\.\s*", "", line).strip() for line in out if line.strip()]
        if len(cleaned) != len(texts):  # fall back rather than misalign
            raise ValueError("translation line count mismatch")
        return cleaned
