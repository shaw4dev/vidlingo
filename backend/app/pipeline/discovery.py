"""Discover YouTube video IDs to ingest — so the library is built by pointing
at sources, not by hand-collecting IDs.

A `VideoSource` yields `VideoCandidate`s (id + metadata). Three concrete sources
wrap the YouTube Data API v3:

    PlaylistSource  — every video in a playlist          (1 quota unit / 50 ids)
    ChannelSource   — a channel's uploads                 (1 unit + 1 to resolve)
    SearchSource    — keyword/topic search, captioned     (100 units / call)

The API layer (`YouTubeDataAPI`) is a thin stdlib-only REST client, imported
lazily and injected, so sources are fully testable offline with a fake client.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

_API_BASE = "https://www.googleapis.com/youtube/v3"

# A lesson is a video plus its whole transcript, so length is a content decision,
# not a detail. Under a minute yields too few sentences to be worth a lesson;
# a channel's 40-minute "best of season 5" compilation is a different thing
# entirely — jump-cut between unrelated scenes, and one lesson nobody finishes.
DEFAULT_MIN_DURATION_S = 60
DEFAULT_MAX_DURATION_S = 900

_ISO_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_iso_duration(value: str | None) -> int | None:
    """YouTube's ISO-8601 duration -> seconds. None if unparseable (live
    streams report P0D), which callers treat as 'unknown, don't ingest'."""
    m = _ISO_DURATION.match(value or "")
    if not m:
        return None
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


class DiscoveryError(Exception):
    """A discovery/API call failed (network, quota, bad key)."""


@dataclass
class VideoCandidate:
    youtube_id: str
    title: str
    channel: str | None = None
    source_tag: str | None = None  # which source surfaced it (for logging/theme)


class YouTubeDataAPI:
    """Minimal YouTube Data API v3 client (stdlib urllib, no extra deps).

    Only the read endpoints the sources need. Paginates transparently up to
    `max_results`. Raises DiscoveryError on transport/HTTP errors.
    """

    def __init__(self, api_key: str, *, timeout: float = 15.0):
        if not api_key:
            raise DiscoveryError("YOUTUBE_API_KEY is not set")
        self._key = api_key
        self._timeout = timeout

    def _get(self, endpoint: str, params: dict) -> dict:
        query = urllib.parse.urlencode({**params, "key": self._key})
        url = f"{_API_BASE}/{endpoint}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # quota/key errors arrive as 403
            body = exc.read().decode("utf-8", "replace")
            raise DiscoveryError(f"YouTube API {exc.code}: {body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise DiscoveryError(f"YouTube API unreachable: {exc.reason}") from exc

    def _paged(self, endpoint: str, params: dict, max_results: int) -> list[dict]:
        items: list[dict] = []
        page_token: str | None = None
        while len(items) < max_results:
            page = {**params, "maxResults": min(50, max_results - len(items))}
            if page_token:
                page["pageToken"] = page_token
            data = self._get(endpoint, page)
            items.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items[:max_results]

    def search_videos(self, query: str, max_results: int = 25) -> list[VideoCandidate]:
        """search.list restricted to captioned, embeddable English videos.

        100 units/call. `videoEmbeddable` matters as much as `videoCaption`: a
        video that forbids off-site embedding is a blank IFrame in the reader,
        so there's no point ingesting it. The filter is a search.list feature
        only — playlist/channel candidates can't be pre-screened this way.
        """
        items = self._paged(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "videoCaption": "closedCaption",
                "videoEmbeddable": "true",
                "relevanceLanguage": "en",
                "safeSearch": "strict",
            },
            max_results,
        )
        out = []
        for it in items:
            vid = it.get("id", {}).get("videoId")
            sn = it.get("snippet", {})
            if vid:
                out.append(
                    VideoCandidate(
                        vid, sn.get("title", ""), sn.get("channelTitle"), f"search:{query}"
                    )
                )
        return out

    def playlist_video_ids(self, playlist_id: str, max_results: int = 200) -> list[VideoCandidate]:
        items = self._paged(
            "playlistItems",
            {"part": "snippet,contentDetails", "playlistId": playlist_id},
            max_results,
        )
        out = []
        for it in items:
            vid = it.get("contentDetails", {}).get("videoId")
            sn = it.get("snippet", {})
            if vid:
                out.append(
                    VideoCandidate(
                        vid, sn.get("title", ""), sn.get("channelTitle"), f"playlist:{playlist_id}"
                    )
                )
        return out

    def screen_playable(
        self,
        candidates: list[VideoCandidate],
        *,
        min_duration_s: int = DEFAULT_MIN_DURATION_S,
        max_duration_s: int = DEFAULT_MAX_DURATION_S,
    ) -> list[VideoCandidate]:
        """Drop candidates that would waste a caption fetch, preserving order.

        `search_videos` gets embeddability for free as a query parameter;
        playlist and channel candidates have no such filter, so they arrive
        unscreened and the first sign of trouble is a blank IFrame in the
        reader — or a 40-minute compilation ingested as one lesson. videos.list
        costs 1 unit per 50 ids and answers both questions, which is far
        cheaper than the caption fetch it avoids (those are rate-limited by IP,
        the scarcest budget the pipeline has).
        """
        if not candidates:
            return []

        keep: set[str] = set()
        ids = [c.youtube_id for c in candidates]
        for start in range(0, len(ids), 50):
            batch = ids[start : start + 50]
            data = self._get(
                "videos", {"part": "contentDetails,status", "id": ",".join(batch)}
            )
            for item in data.get("items", []):
                status = item.get("status", {})
                seconds = parse_iso_duration(item.get("contentDetails", {}).get("duration"))
                if (
                    status.get("embeddable")
                    and status.get("privacyStatus") == "public"
                    and seconds is not None
                    and min_duration_s <= seconds <= max_duration_s
                ):
                    keep.add(item["id"])

        return [c for c in candidates if c.youtube_id in keep]

    def channel_uploads_playlist(self, channel_id: str) -> str:
        """Resolve a channel's 'uploads' playlist id (needed to list its videos)."""
        data = self._get("channels", {"part": "contentDetails", "id": channel_id})
        items = data.get("items", [])
        if not items:
            raise DiscoveryError(f"channel not found: {channel_id}")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


# ---- sources ---------------------------------------------------------------

class VideoSource(Protocol):
    def discover(self, api: YouTubeDataAPI, limit: int) -> list[VideoCandidate]:
        ...


@dataclass
class PlaylistSource:
    playlist_id: str
    theme: str | None = None
    # playlistItems can't pre-filter, and screening throws candidates away, so
    # ask for more than we need. It costs 1 unit per extra 50 ids.
    overfetch = 3

    def discover(self, api: YouTubeDataAPI, limit: int) -> list[VideoCandidate]:
        return _tag_theme(api.playlist_video_ids(self.playlist_id, limit), self.theme)


@dataclass
class ChannelSource:
    channel_id: str
    theme: str | None = None
    overfetch = 3

    def discover(self, api: YouTubeDataAPI, limit: int) -> list[VideoCandidate]:
        uploads = api.channel_uploads_playlist(self.channel_id)
        return _tag_theme(api.playlist_video_ids(uploads, limit), self.theme)


@dataclass
class SearchSource:
    query: str
    theme: str | None = None
    # 100 units a call — over-fetching here is the expensive mistake, and
    # search.list has already filtered for captions and embeddability.
    overfetch = 1

    def discover(self, api: YouTubeDataAPI, limit: int) -> list[VideoCandidate]:
        return _tag_theme(api.search_videos(self.query, limit), self.theme)


def _tag_theme(cands: list[VideoCandidate], theme: str | None) -> list[VideoCandidate]:
    if theme:
        for c in cands:
            c.source_tag = theme
    return cands
