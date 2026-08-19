"""T13: word definitions — provider parsing, DB cache, and the API endpoint.

Everything here runs offline: the dictionary provider is a fake injected via the
FastAPI dependency, so no test ever touches dictionaryapi.dev or Anthropic.
"""

import json

import pytest

from app.content.dictionary import (
    Definition,
    DictionaryError,
    FreeDictionaryProvider,
    Sense,
    get_dictionary_provider,
    get_gloss_provider,
    lookup_definition,
)
from app.db.models import DictionaryEntry
from app.main import app


class FakeProvider:
    """Records every lookup so we can assert the cache actually prevents them."""

    name = "fake"

    def __init__(self, entries: dict[str, Definition] | None = None):
        self.entries = entries or {}
        self.calls: list[str] = []

    def lookup(self, word: str) -> Definition | None:
        self.calls.append(word)
        return self.entries.get(word)


class BoomProvider:
    name = "boom"

    def lookup(self, word: str) -> Definition | None:
        raise DictionaryError("dictionary API unreachable: boom")


def _run(lemma: str) -> Definition:
    return Definition(
        lemma=lemma,
        phonetic="/rʌn/",
        audio_url="https://audio.example/run.mp3",
        senses=[Sense(pos="verb", definition="To move swiftly on foot.", example="I run daily.")],
        provider="fake",
    )


# ---- provider parsing ------------------------------------------------------

def test_free_dictionary_parses_phonetic_audio_and_senses():
    payload = [
        {
            "word": "run",
            "phonetics": [{"text": "", "audio": ""}, {"text": "/rʌn/", "audio": "https://a/run.mp3"}],
            "meanings": [
                {
                    "partOfSpeech": "verb",
                    "definitions": [
                        {"definition": "To move swiftly on foot.", "example": "I run daily."},
                        {"definition": "To operate."},
                    ],
                }
            ],
        }
    ]
    parsed = FreeDictionaryProvider()._parse("run", payload)
    assert parsed is not None
    assert parsed.phonetic == "/rʌn/"
    assert parsed.audio_url == "https://a/run.mp3"  # skips the empty audio entry
    assert [s.definition for s in parsed.senses] == ["To move swiftly on foot.", "To operate."]
    assert parsed.senses[0].pos == "verb"


def test_free_dictionary_caps_sense_count():
    payload = [
        {
            "meanings": [
                {
                    "partOfSpeech": "noun",
                    "definitions": [{"definition": f"sense {i}"} for i in range(20)],
                }
            ]
        }
    ]
    parsed = FreeDictionaryProvider(max_senses=3)._parse("x", payload)
    assert parsed is not None
    assert len(parsed.senses) == 3


@pytest.mark.parametrize("payload", [[], {"title": "No Definitions Found"}, [{}]])
def test_free_dictionary_treats_empty_payloads_as_a_miss(payload):
    assert FreeDictionaryProvider()._parse("zzz", payload) is None


# ---- cached lookup ---------------------------------------------------------

def test_lookup_caches_so_the_provider_is_hit_once(db):
    provider = FakeProvider({"run": _run("run")})

    first = lookup_definition(db, ["run"], provider)
    second = lookup_definition(db, ["run"], provider)

    assert first is not None and second is not None
    assert first.senses == second.senses
    assert provider.calls == ["run"], "second lookup should be served from the DB"
    assert db.get(DictionaryEntry, "run") is not None


def test_lookup_falls_back_to_the_surface_form(db):
    # "series" lemmatizes to "sery", which no dictionary knows.
    provider = FakeProvider({"series": _run("series")})

    found = lookup_definition(db, ["sery", "series"], provider)

    assert found is not None
    assert found.lemma == "series"
    assert provider.calls == ["sery", "series"]


def test_lookup_returns_none_when_nothing_matches(db):
    provider = FakeProvider()
    assert lookup_definition(db, ["zzzz"], provider) is None
    assert db.get(DictionaryEntry, "zzzz") is None, "misses must not be cached"


def test_gloss_is_attached_and_persisted(db):
    class Gloss:
        def gloss(self, word, senses):
            return "跑，奔跑"

    found = lookup_definition(db, ["run"], FakeProvider({"run": _run("run")}), Gloss())

    assert found is not None and found.gloss_zh == "跑，奔跑"
    assert db.get(DictionaryEntry, "run").gloss_zh == "跑，奔跑"


def test_gloss_failure_still_yields_a_definition(db):
    class Gloss:
        def gloss(self, word, senses):
            raise RuntimeError("no api key")

    found = lookup_definition(db, ["run"], FakeProvider({"run": _run("run")}), Gloss())

    assert found is not None
    assert found.gloss_zh is None
    assert found.senses  # the English half survives


def test_corrupt_cache_row_degrades_instead_of_raising(db):
    db.add(DictionaryEntry(lemma="run", senses="not json", provider="fake"))
    db.commit()

    found = lookup_definition(db, ["run"], FakeProvider())

    assert found is not None and found.senses == []


# ---- endpoint --------------------------------------------------------------

def _override(client, provider, gloss=None):
    app.dependency_overrides[get_dictionary_provider] = lambda: provider
    app.dependency_overrides[get_gloss_provider] = lambda: gloss


def test_definition_endpoint_returns_the_card_payload(client):
    _override(client, FakeProvider({"run": _run("run")}))

    res = client.get("/api/words/run/definition")

    assert res.status_code == 200
    body = res.json()
    assert body["lemma"] == "run"
    assert body["phonetic"] == "/rʌn/"
    assert body["audio_url"] == "https://audio.example/run.mp3"
    assert body["senses"][0]["pos"] == "verb"
    assert body["senses"][0]["example"] == "I run daily."


def test_definition_endpoint_lemmatizes_the_tapped_surface_form(client):
    provider = FakeProvider({"run": _run("run")})
    _override(client, provider)

    res = client.get("/api/words/running/definition")

    assert res.status_code == 200
    assert res.json()["lemma"] == "run"


def test_definition_endpoint_404s_for_an_unknown_word(client):
    _override(client, FakeProvider())
    assert client.get("/api/words/zzzz/definition").status_code == 404


def test_definition_endpoint_502s_when_the_dictionary_is_unreachable(client):
    _override(client, BoomProvider())
    # An unreachable dictionary is not the same as an unknown word.
    assert client.get("/api/words/run/definition").status_code == 502


def test_definition_endpoint_serves_a_cached_row_without_the_provider(client, db):
    db.add(
        DictionaryEntry(
            lemma="run",
            phonetic="/rʌn/",
            gloss_zh="跑",
            senses=json.dumps([{"pos": "verb", "definition": "To move swiftly.", "example": None}]),
            provider="fake",
        )
    )
    db.commit()
    provider = FakeProvider()
    _override(client, provider)

    body = client.get("/api/words/run/definition").json()

    assert body["gloss_zh"] == "跑"
    assert provider.calls == []


def test_free_dictionary_identifies_itself(monkeypatch):
    """Cloudflare 403s (error 1010) the default urllib agent, so the request
    must carry a real User-Agent. Regression guard: dropping the header turns
    every word card into a 502."""
    import urllib.request

    from app.content import dictionary as dict_mod

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps([{"word": "run", "phonetic": "/rʌn/"}]).encode()

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        captured["url"] = req.full_url
        captured["ua"] = req.get_header("User-agent")
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dict_mod.FreeDictionaryProvider().lookup("run")

    assert captured["url"].endswith("/run")
    assert captured["ua"] == dict_mod._USER_AGENT
    assert "urllib" not in str(captured["ua"]).lower()
