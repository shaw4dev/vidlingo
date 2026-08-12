"""The two content-sourcing jobs that fill the library without hand-collecting IDs.

    seed_corpus   — batch: point at sources (channels/playlists/searches),
                    ingest their captioned videos. Builds broad coverage so the
                    common words a learner taps are already indexed.

    backfill_word — on demand: a tapped word with too few occurrences triggers a
                    search, and only videos whose captions ACTUALLY contain the
                    lemma get ingested. A WordSearch cache stops a repeated miss
                    from re-spending API quota.

Both reuse the existing ingest pipeline and are network-injected (api client +
caption fetcher), so they're fully testable offline with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Lesson, WordIndex, WordSearch
from app.pipeline.captions import CaptionFetcher, CaptionsBlockedError, NoCaptionsError
from app.pipeline.discovery import VideoCandidate, VideoSource, YouTubeDataAPI
from app.pipeline.nlp import Translator, lemmatize, tokenize
from app.pipeline.pipeline import LessonMeta, ingest_from_cues


def _lesson_id(youtube_id: str) -> str:
    return f"yt_{youtube_id}"


def _already_ingested(session: Session, youtube_id: str) -> bool:
    return session.get(Lesson, _lesson_id(youtube_id)) is not None


@dataclass
class SeedReport:
    ingested: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    skipped_no_captions: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (id, error)
    blocked: str | None = None  # set when YouTube cut us off; batch stopped early

    @property
    def summary(self) -> str:
        base = (
            f"ingested={len(self.ingested)} existing={len(self.skipped_existing)} "
            f"no_captions={len(self.skipped_no_captions)} failed={len(self.failed)}"
        )
        return f"{base} ABORTED (blocked: {self.blocked})" if self.blocked else base


def _ingest_candidate(
    session: Session,
    cand: VideoCandidate,
    fetcher: CaptionFetcher,
    translator: Translator,
    default_theme: str,
) -> None:
    """Fetch + ingest one candidate. Raises NoCaptionsError up to the caller."""
    cues = fetcher.fetch(cand.youtube_id)
    meta = LessonMeta(
        youtube_id=cand.youtube_id,
        title=cand.title or cand.youtube_id,
        theme=cand.source_tag or default_theme,
        source=cand.channel,
    )
    ingest_from_cues(session, meta, cues, translator)


def seed_corpus(
    session: Session,
    sources: list[VideoSource],
    api: YouTubeDataAPI,
    fetcher: CaptionFetcher,
    translator: Translator,
    *,
    per_source: int = 25,
    default_theme: str = "general",
) -> SeedReport:
    """Discover candidates from each source and ingest the ones with captions."""
    report = SeedReport()
    seen: set[str] = set()
    for source in sources:
        for cand in source.discover(api, per_source):
            if cand.youtube_id in seen:
                continue
            seen.add(cand.youtube_id)
            if _already_ingested(session, cand.youtube_id):
                report.skipped_existing.append(cand.youtube_id)
                continue
            try:
                _ingest_candidate(session, cand, fetcher, translator, default_theme)
                report.ingested.append(cand.youtube_id)
            except NoCaptionsError:
                report.skipped_no_captions.append(cand.youtube_id)
            except CaptionsBlockedError as exc:
                # Not this video's fault — every remaining fetch would fail the
                # same way, and retrying deepens the block. Keep what we got.
                report.blocked = str(exc)
                return report
            except Exception as exc:  # noqa: BLE001 — one bad video shouldn't halt the batch
                report.failed.append((cand.youtube_id, str(exc)))
    return report


@dataclass
class BackfillReport:
    lemma: str
    coverage_before: int
    ingested: list[str] = field(default_factory=list)
    already_covered: bool = False
    cached_skip: bool = False  # searched before; didn't spend quota again
    blocked: str | None = None  # YouTube cut us off; search NOT cached, safe to retry

    @property
    def summary(self) -> str:
        if self.already_covered:
            return f"{self.lemma}: already covered ({self.coverage_before} occ) — no search"
        if self.cached_skip:
            return f"{self.lemma}: searched previously — skipped to save quota"
        if self.blocked:
            return (
                f"{self.lemma}: +{len(self.ingested)} ingested, then ABORTED "
                f"(blocked: {self.blocked}) — not cached, retry later"
            )
        return f"{self.lemma}: +{len(self.ingested)} video(s) ingested"


def _coverage(session: Session, lemma: str) -> int:
    return session.scalar(
        select(func.count()).select_from(WordIndex).where(func.lower(WordIndex.lemma) == lemma)
    ) or 0


def _captions_contain(cues, lemma: str) -> bool:
    """True if `lemma` appears in the transcript (matched on lemmatized tokens,
    so 'running' matches a search for 'run')."""
    for cue in cues:
        for tok in tokenize(cue.text):
            if tok["lemma"] == lemma:
                return True
    return False


def backfill_word(
    session: Session,
    lemma: str,
    api: YouTubeDataAPI,
    fetcher: CaptionFetcher,
    translator: Translator,
    *,
    min_coverage: int = 3,
    max_ingest: int = 3,
    per_search: int = 10,
    default_theme: str = "discovered",
    force: bool = False,
) -> BackfillReport:
    """Ingest videos whose captions contain `lemma`, if it's under-covered.

    Short-circuits (no quota spent) when the word already has >= min_coverage
    occurrences, or when we've searched for it before (unless `force`).
    """
    lemma = lemmatize(lemma.strip().lower())
    before = _coverage(session, lemma)
    report = BackfillReport(lemma=lemma, coverage_before=before)

    if before >= min_coverage:
        report.already_covered = True
        return report

    if not force and session.get(WordSearch, lemma) is not None:
        report.cached_skip = True
        return report

    for cand in api.search_videos(lemma, per_search):
        if len(report.ingested) >= max_ingest:
            break
        if _already_ingested(session, cand.youtube_id):
            continue
        try:
            cues = fetcher.fetch(cand.youtube_id)
        except NoCaptionsError:
            continue
        except CaptionsBlockedError as exc:
            # Bail out WITHOUT caching the search: the lemma wasn't really
            # searched, and a cache entry here would skip it forever.
            report.blocked = str(exc)
            session.commit()  # keep whatever was ingested before the block
            return report
        if not _captions_contain(cues, lemma):
            continue  # search matched title/metadata, not the actual word — skip
        meta = LessonMeta(
            youtube_id=cand.youtube_id,
            title=cand.title or cand.youtube_id,
            theme=default_theme,
            source=cand.channel,
        )
        ingest_from_cues(session, meta, cues, translator)
        report.ingested.append(cand.youtube_id)

    # Record the search either way, so a fruitless miss isn't retried for free.
    record = session.get(WordSearch, lemma)
    if record is None:
        session.add(WordSearch(lemma=lemma, ingested_count=len(report.ingested)))
    else:
        record.ingested_count += len(report.ingested)
    session.commit()
    return report
