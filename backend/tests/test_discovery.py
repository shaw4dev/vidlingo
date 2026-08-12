import pytest

from app.pipeline.discovery import (
    ChannelSource,
    DiscoveryError,
    PlaylistSource,
    SearchSource,
    VideoCandidate,
    YouTubeDataAPI,
)


class FakeAPI:
    """Stand-in for YouTubeDataAPI used to test the source wrappers."""

    def __init__(self, *, search=None, playlists=None, uploads=None):
        self._search = search or {}
        self._playlists = playlists or {}
        self._uploads = uploads or {}

    def search_videos(self, query, max_results=25):
        return self._search.get(query, [])[:max_results]

    def playlist_video_ids(self, pid, max_results=200):
        return self._playlists.get(pid, [])[:max_results]

    def channel_uploads_playlist(self, cid):
        return self._uploads[cid]


# ---- sources ---------------------------------------------------------------

def test_playlist_source_tags_theme():
    api = FakeAPI(playlists={"PL1": [VideoCandidate("v1", "A"), VideoCandidate("v2", "B")]})
    cands = PlaylistSource("PL1", theme="small_talk").discover(api, 10)
    assert [c.youtube_id for c in cands] == ["v1", "v2"]
    assert all(c.source_tag == "small_talk" for c in cands)


def test_channel_source_resolves_uploads_then_lists():
    api = FakeAPI(
        uploads={"UC1": "UU1"},
        playlists={"UU1": [VideoCandidate("v9", "Vid")]},
    )
    cands = ChannelSource("UC1", theme="interviews").discover(api, 10)
    assert [c.youtube_id for c in cands] == ["v9"]
    assert cands[0].source_tag == "interviews"


def test_search_source_passes_query():
    api = FakeAPI(search={"greetings": [VideoCandidate("v3", "Hi")]})
    cands = SearchSource("greetings").discover(api, 5)
    assert cands[0].youtube_id == "v3"


# ---- API client (parsing + pagination, no network) -------------------------

def test_api_requires_key():
    with pytest.raises(DiscoveryError):
        YouTubeDataAPI("")


def test_search_videos_parses_and_paginates(monkeypatch):
    api = YouTubeDataAPI("fake-key")
    pages = [
        {
            "items": [
                {"id": {"videoId": "a"}, "snippet": {"title": "A", "channelTitle": "Ch"}},
                {"id": {"videoId": "b"}, "snippet": {"title": "B"}},
            ],
            "nextPageToken": "p2",
        },
        {"items": [{"id": {"videoId": "c"}, "snippet": {"title": "C"}}]},
    ]
    calls = []

    def fake_get(endpoint, params):
        calls.append(params.get("pageToken"))
        return pages[len(calls) - 1]

    monkeypatch.setattr(api, "_get", fake_get)
    cands = api.search_videos("hello", max_results=3)
    assert [c.youtube_id for c in cands] == ["a", "b", "c"]
    assert cands[0].channel == "Ch"
    assert calls == [None, "p2"]  # followed nextPageToken


def test_search_videos_filters_to_captioned_embeddable_videos(monkeypatch):
    """Both filters are load-bearing: no captions means nothing to ingest, and
    a non-embeddable video is a blank IFrame in the reader."""
    api = YouTubeDataAPI("fake-key")
    sent = {}

    def fake_get(endpoint, params):
        sent.update(params)
        return {"items": []}

    monkeypatch.setattr(api, "_get", fake_get)
    api.search_videos("small talk", max_results=5)
    assert sent["type"] == "video"
    assert sent["videoCaption"] == "closedCaption"
    assert sent["videoEmbeddable"] == "true"
    assert sent["q"] == "small talk"


def test_search_videos_respects_max_results(monkeypatch):
    api = YouTubeDataAPI("fake-key")
    page = {"items": [{"id": {"videoId": x}, "snippet": {"title": x}} for x in "abcde"]}
    monkeypatch.setattr(api, "_get", lambda e, p: page)
    assert len(api.search_videos("q", max_results=2)) == 2
