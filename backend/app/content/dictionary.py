"""Word definitions for the word card (T13).

The word card needs: phonetic, part of speech, an English sense or two, and —
since the learner is a native Chinese speaker — a short Chinese gloss. No single
free source gives all four, so this module composes two:

    FreeDictionaryProvider  — dictionaryapi.dev: phonetic + audio + EN senses
                              (free, no key, stdlib-only client)
    ClaudeGlossProvider     — an optional Chinese gloss, when ANTHROPIC_API_KEY
                              is set. Skipped silently otherwise.

Both sit behind Protocols and are injected via a FastAPI dependency, so tests
run fully offline with fakes. Results are cached in `dictionary_entries` — one
network call per lemma, ever — which is what makes tapping words cheap.

The in-context meaning shown on the card is the source sentence's own Chinese
translation, which the LessonPackage already carries; this module only supplies
the word-level entry.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.models import DictionaryEntry

log = logging.getLogger(__name__)

_FREE_DICT_BASE = "https://api.dictionaryapi.dev/api/v2/entries/en"

# Keep the card readable: a long dictionary entry is worse than a short one here.
MAX_SENSES = 4


class DictionaryError(Exception):
    """The dictionary provider was unreachable (network/HTTP), as opposed to
    the word simply not being found (which is a `None` lookup, not an error)."""


@dataclass(frozen=True)
class Sense:
    pos: str | None
    definition: str
    example: str | None = None


@dataclass(frozen=True)
class Definition:
    lemma: str
    phonetic: str | None = None
    audio_url: str | None = None
    gloss_zh: str | None = None
    senses: list[Sense] = field(default_factory=list)
    provider: str = "unknown"


class DictionaryProvider(Protocol):
    name: str

    def lookup(self, word: str) -> Definition | None:
        """Return a definition, or None if the word simply isn't in the source."""
        ...


class GlossProvider(Protocol):
    def gloss(self, word: str, senses: list[Sense]) -> str | None: ...


# ---- providers -------------------------------------------------------------

class NullDictionaryProvider:
    """Used when no dictionary is configured — every lookup is a clean miss."""

    name = "null"

    def lookup(self, word: str) -> Definition | None:  # noqa: ARG002
        return None


class FreeDictionaryProvider:
    """dictionaryapi.dev — free, keyless, English-only. stdlib urllib, matching
    the discovery client's dependency-light style."""

    name = "dictionaryapi.dev"

    def __init__(self, *, timeout: float = 8.0, max_senses: int = MAX_SENSES):
        self._timeout = timeout
        self._max_senses = max_senses

    def lookup(self, word: str) -> Definition | None:
        url = f"{_FREE_DICT_BASE}/{urllib.parse.quote(word)}"
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:  # noqa: S310
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # not a failure: the word just isn't there
            raise DictionaryError(f"dictionary API {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise DictionaryError(f"dictionary API unreachable: {exc.reason}") from exc
        except (ValueError, TimeoutError) as exc:
            raise DictionaryError(f"dictionary API returned junk: {exc}") from exc

        return self._parse(word, payload)

    def _parse(self, word: str, payload: object) -> Definition | None:
        if not isinstance(payload, list) or not payload:
            return None
        entries = [e for e in payload if isinstance(e, dict)]
        if not entries:
            return None

        phonetic = None
        audio_url = None
        senses: list[Sense] = []
        for entry in entries:
            phonetic = phonetic or entry.get("phonetic")
            for ph in entry.get("phonetics") or []:
                if not isinstance(ph, dict):
                    continue
                phonetic = phonetic or ph.get("text")
                audio_url = audio_url or (ph.get("audio") or None)
            for meaning in entry.get("meanings") or []:
                if not isinstance(meaning, dict):
                    continue
                pos = meaning.get("partOfSpeech")
                for d in meaning.get("definitions") or []:
                    if not isinstance(d, dict) or not d.get("definition"):
                        continue
                    senses.append(
                        Sense(pos=pos, definition=d["definition"], example=d.get("example"))
                    )
                    if len(senses) >= self._max_senses:
                        break
                if len(senses) >= self._max_senses:
                    break
            if len(senses) >= self._max_senses:
                break

        if not senses and not phonetic:
            return None
        return Definition(
            lemma=word,
            phonetic=phonetic,
            audio_url=audio_url,
            senses=senses,
            provider=self.name,
        )


class ClaudeGlossProvider:
    """Short Simplified-Chinese gloss via the Anthropic API.

    One cheap call per *new* lemma (the result is cached in the DB forever), so
    this costs roughly one request per distinct word she ever taps.
    """

    def __init__(self, model: str = "claude-opus-5"):
        self.model = model

    def gloss(self, word: str, senses: list[Sense]) -> str | None:
        from anthropic import Anthropic  # noqa: PLC0415  (optional dependency)

        context = "\n".join(f"- ({s.pos or '?'}) {s.definition}" for s in senses[:MAX_SENSES])
        msg = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
            model=self.model,
            # A gloss is a handful of characters, and it's cached forever after
            # the first tap — the cap is the only cost control needed here.
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Give the Simplified Chinese meaning of the English word "{word}".\n'
                        f"Its English senses:\n{context}\n\n"
                        "Reply with ONLY the Chinese gloss — a few comma-separated "
                        "equivalents, no pinyin, no explanation, no quotes."
                    ),
                }
            ],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None


# ---- cached lookup ---------------------------------------------------------

def _to_definition(row: DictionaryEntry) -> Definition:
    try:
        raw = json.loads(row.senses)
    except ValueError:  # corrupt cache row — degrade to no senses rather than 500
        raw = []
    return Definition(
        lemma=row.lemma,
        phonetic=row.phonetic,
        audio_url=row.audio_url,
        gloss_zh=row.gloss_zh,
        senses=[Sense(**s) for s in raw if isinstance(s, dict)],
        provider=row.provider,
    )


def lookup_definition(
    session: Session,
    candidates: list[str],
    provider: DictionaryProvider,
    gloss_provider: GlossProvider | None = None,
) -> Definition | None:
    """First cache hit or successful provider lookup across `candidates`, or None.

    Callers pass the lemma first and the raw surface form as a fallback, so a
    word our rule-based lemmatizer mangles ("series" -> "sery") still resolves.
    """
    seen: list[str] = []
    for word in candidates:
        key = word.strip().lower()
        if not key or key in seen:
            continue
        seen.append(key)

        cached = session.get(DictionaryEntry, key)
        if cached is not None:
            return _to_definition(cached)

        found = provider.lookup(key)
        if found is None:
            continue

        gloss = None
        if gloss_provider is not None:
            try:
                gloss = gloss_provider.gloss(key, found.senses)
            except Exception:  # noqa: BLE001 — a missing gloss must not lose the entry
                log.exception("gloss failed for %r", key)

        definition = Definition(
            lemma=key,
            phonetic=found.phonetic,
            audio_url=found.audio_url,
            gloss_zh=gloss,
            senses=found.senses,
            provider=found.provider,
        )
        session.merge(
            DictionaryEntry(
                lemma=key,
                phonetic=definition.phonetic,
                audio_url=definition.audio_url,
                gloss_zh=definition.gloss_zh,
                senses=json.dumps([asdict(s) for s in definition.senses]),
                provider=definition.provider,
            )
        )
        session.commit()
        return definition
    return None


# ---- FastAPI dependencies --------------------------------------------------

_dictionary_provider: DictionaryProvider = FreeDictionaryProvider()


def get_dictionary_provider() -> DictionaryProvider:
    return _dictionary_provider


def get_gloss_provider() -> GlossProvider | None:
    """Chinese glosses only when Anthropic is configured; otherwise the card
    falls back to English senses plus the sentence's own translation."""
    return ClaudeGlossProvider() if os.getenv("ANTHROPIC_API_KEY") else None
