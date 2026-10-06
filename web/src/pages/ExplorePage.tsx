// The front door: a pitch for people who have never seen this, over a library
// that anyone can walk into without an account.
//
// The old landing page was a flat grid of everything with three difficulty
// chips over it. That is a file listing. A corpus of real television is the
// only thing this product has that a flashcard app does not, and a listing
// hides it: nothing on that page said "Friends", "The Office", "a TED talk",
// or "two minutes". Shelves say it in one screen.
//
// Then it got every shelf at once — one per show, plus by length, plus by
// level: nine rows of thumbnails, 3,500px of them. That is a video site, and
// it buried the one thing a visitor needs to learn before any clip, which is
// what this does that YouTube doesn't. So below the hero a visitor now gets,
// in order: how it works (shown, not listed), one row of clips to start with,
// the shows as five posters instead of five rows, and a way in. Each section
// makes one point; the library holds the rest.
//
// The hero is auth-aware. A visitor gets the argument — what this is, what it
// costs (nothing, to try), one button into a real lesson. Someone already
// signed in has heard the argument; they get the clip they were watching.
import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { Shelf } from '../components/Shelf'
import { useAuth } from '../auth/AuthContext'
import { LessonCard } from '../features/library/LessonCard'
import { clipTitle, showOf, showsByCatalogue, type Show } from '../features/library/shows'
import {
  formatDuration,
  nearestLevel,
  thumbnailUrl,
  useLessons,
} from '../features/library/useLessons'
import { useLearnerPrefs } from '../features/prefs/useLearnerPrefs'
import {
  isFinished,
  progressOf,
  useWatchHistory,
  type WatchMark,
} from '../features/progress/useWatchHistory'
import type { LessonSummary } from '../lib/api'

/** Clips this long or shorter are the "one minute spare" shelf. */
const QUICK_MS = 2 * 60 * 1000

const LEVEL_BLURB: Record<string, string> = {
  easy: 'Short lines and everyday vocabulary.',
  medium: 'Natural pace, some idiom, the occasional rewind.',
  hard: 'Dense, fast and unscripted.',
}

export function ExplorePage() {
  const { lessons, error } = useLessons()
  const { user } = useAuth()
  const prefs = useLearnerPrefs()
  const history = useWatchHistory()

  const byId = useMemo(() => new Map((lessons ?? []).map((l) => [l.id, l])), [lessons])

  // Only clips still in the corpus, and not ones she has already finished.
  const continuing = useMemo(
    () =>
      history
        .filter((m) => byId.has(m.lessonId) && !isFinished(m))
        .map((m) => ({ mark: m, lesson: byId.get(m.lessonId)! })),
    [history, byId],
  )

  const shows = useMemo(() => showsByCatalogue(lessons ?? []), [lessons])

  // Not `difficulty === prefs.level`: the corpus holds no easy clips, so a
  // beginner asking for easy would get an empty shelf where the whole point is
  // to give them somewhere to start. Nearest available wins, and the blurb
  // below says which level she is actually looking at.
  const shelfLevel = useMemo(() => nearestLevel(lessons ?? [], prefs.level), [lessons, prefs.level])
  const forLevel = useMemo(
    () => (shelfLevel ? (lessons ?? []).filter((l) => l.difficulty === shelfLevel) : []),
    [lessons, shelfLevel],
  )

  const quick = useMemo(
    () =>
      (lessons ?? [])
        .filter((l) => l.duration_ms <= QUICK_MS)
        .sort((a, b) => a.duration_ms - b.duration_ms),
    [lessons],
  )

  // The hero rotates by day rather than by render: a page that shows a
  // different clip every time you touch it feels broken, and a page that
  // shows the same one forever feels dead.
  const featured = useMemo(() => pickFeatured(lessons ?? []), [lessons])
  const resume = continuing[0]

  return (
    <div className="page wide explore">
      <AppHeader />

      {error && <p className="error">{error}</p>}

      {user ? (
        <ReturningHero
          lesson={resume?.lesson ?? featured}
          mark={resume?.mark}
          name={user.username}
        />
      ) : (
        <PitchHero lesson={featured} />
      )}

      {!user && <HowItWorks />}

      {!lessons && !error && <ShelfSkeleton />}

      {continuing.length > 0 && (
        <Shelf title="Continue watching">
          {continuing.map(({ mark, lesson }) => (
            <LessonCard
              key={lesson.id}
              lesson={lesson}
              resumeIdx={mark.sentenceIdx}
              progress={progressOf(mark)}
            />
          ))}
        </Shelf>
      )}

      {shelfLevel && forLevel.length > 2 && (
        <Shelf
          title={prefs.onboardedAt ? 'Picked for your level' : 'Good place to start'}
          blurb={
            shelfLevel === prefs.level
              ? LEVEL_BLURB[shelfLevel]
              : `${LEVEL_BLURB[shelfLevel]} The closest we have to the level you picked.`
          }
          seeAllTo={`/library?level=${shelfLevel}`}
        >
          {forLevel.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </Shelf>
      )}

      {shows.length > 1 && <ShowTiles shows={shows} />}

      {user && quick.length > 2 && (
        <Shelf title="Under two minutes" blurb="One scene, start to finish, on a coffee break.">
          {quick.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </Shelf>
      )}

      {!user && <ClosingCta lesson={featured} />}
    </div>
  )
}

/** Longest-first, then one per day — the long ones have the best stills and
 *  the most to say. */
function pickFeatured(lessons: LessonSummary[]): LessonSummary | null {
  if (lessons.length === 0) return null
  const candidates = [...lessons]
    .filter((l) => l.youtube_id)
    .sort((a, b) => b.duration_ms - a.duration_ms)
    .slice(0, 5)
  if (candidates.length === 0) return lessons[0]
  const day = Math.floor(Date.now() / 86_400_000)
  return candidates[day % candidates.length]
}

function backdrop(lesson: LessonSummary | null): string | undefined {
  // maxres is the one YouTube still wide enough not to look like a thumbnail
  // stretched across a hero; hqdefault is the fallback that always exists.
  return lesson?.youtube_id
    ? `https://i.ytimg.com/vi/${lesson.youtube_id}/maxresdefault.jpg`
    : thumbnailUrl(lesson?.youtube_id ?? null)
}

/**
 * The still, twice: blurred to the edges of the hero, and crisp inside a card.
 *
 * Full-bleed was the obvious first try and it looked like a mistake. A YouTube
 * thumbnail is not a film still — it is a poster with two-foot letters burned
 * into it ("I HAVE EGG IN MY GROSS…"), composed to survive being 200px wide in
 * a sidebar. Stretched across a hero behind the headline, that text fights the
 * headline and wins, and it is different clickbait every day, so no amount of
 * scrim tuning fixes it for tomorrow's clip.
 *
 * Blurring the copy that reaches the edges turns whatever it is into a colour
 * wash taken from the actual video, and the unblurred one stays small enough
 * to read as a poster rather than as a billboard.
 */
function HeroFrame({
  img,
  compact,
  children,
  card,
}: {
  img?: string
  compact?: boolean
  children: ReactNode
  card: ReactNode
}) {
  return (
    <section className={compact ? 'hero compact' : 'hero'}>
      {img && (
        <div className="hero-bg" style={{ backgroundImage: `url(${img})` }} aria-hidden="true" />
      )}
      <div className="hero-shade" aria-hidden="true" />
      <div className="hero-body">
        <div className="hero-copy">{children}</div>
        <div className="hero-aside">{card}</div>
      </div>
    </section>
  )
}

/** The crisp poster: the clip itself, as a card you can click. */
function HeroPoster({
  lesson,
  to,
  caption,
  progress,
}: {
  lesson: LessonSummary
  to: string
  caption: string
  progress?: number
}) {
  const thumb = thumbnailUrl(lesson.youtube_id)
  return (
    <Link to={to} className="hero-poster">
      <span
        className="hero-poster-still"
        style={thumb ? { backgroundImage: `url(${thumb})` } : undefined}
      >
        <span className="hero-poster-play" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26">
            <polygon points="8,5 20,12 8,19" fill="currentColor" />
          </svg>
        </span>
        {progress != null && progress > 0 && (
          <span className="thumb-progress" aria-hidden="true">
            <span style={{ width: `${Math.round(progress * 100)}%` }} />
          </span>
        )}
      </span>
      <span className="hero-poster-title">{clipTitle(lesson)}</span>
      <span className="hero-poster-meta muted small">{caption}</span>
    </Link>
  )
}

function PitchHero({ lesson }: { lesson: LessonSummary | null }) {
  return (
    <HeroFrame
      img={backdrop(lesson)}
      card={
        lesson && (
          <HeroPoster
            lesson={lesson}
            to={`/reader/${lesson.id}`}
            caption={`${showOf(lesson).label} · ${formatDuration(lesson.duration_ms)} · no account needed`}
          />
        )
      }
    >
      <p className="hero-eyebrow">Real television · bilingual subtitles</p>
      <h1 className="hero-title">Learn English from the shows you already watch.</h1>
      <p className="hero-sub">
        Friends, The Office and a TED talk or two, cut into study-sized scenes. Tap a word for its
        meaning; keep the ones worth keeping.
      </p>
      <div className="hero-actions">
        {lesson && (
          <Link to={`/reader/${lesson.id}`} className="btn-hero">
            ▶ Try a lesson
          </Link>
        )}
        <Link to="/login" state={{ mode: 'register' }} className="btn-hero ghost">
          Sign up free
        </Link>
      </div>
      <p className="hero-note muted small">
        No account needed to watch, look words up, or use the player. You sign in when you want to
        keep a word.
      </p>
    </HeroFrame>
  )
}

function ReturningHero({
  lesson,
  mark,
  name,
}: {
  lesson: LessonSummary | null
  mark?: WatchMark
  name: string
}) {
  if (!lesson) return null
  const to = mark ? `/reader/${lesson.id}?s=${mark.sentenceIdx}` : `/reader/${lesson.id}`
  const meta = `${showOf(lesson).label} · ${formatDuration(lesson.duration_ms)}`
  return (
    <HeroFrame
      compact
      img={backdrop(lesson)}
      card={
        <HeroPoster
          lesson={lesson}
          to={to}
          caption={
            mark ? `${meta} · ${Math.round(progressOf(mark) * 100)}% through` : meta
          }
          progress={mark ? progressOf(mark) : undefined}
        />
      }
    >
      <p className="hero-eyebrow">Welcome back, {name}</p>
      <h1 className="hero-title small">
        {mark ? 'Pick up where you stopped.' : 'Something new to watch.'}
      </h1>
      <p className="hero-sub">
        {mark
          ? 'Your place is kept per clip, so a half-watched scene is still half-watched tomorrow.'
          : 'Nothing half-finished — here is the one we would start with today.'}
      </p>
      <div className="hero-actions">
        <Link to={to} className="btn-hero">
          {mark ? '▶ Resume' : '▶ Watch'}
        </Link>
        <Link to="/review" className="btn-hero ghost">
          Review due words
        </Link>
      </div>
    </HeroFrame>
  )
}

/**
 * The three things the product does, each shown as a small piece of the real
 * interface rather than described. Built from markup, not screenshots: it
 * stays sharp, follows the palette, and cannot drift from the app into a
 * picture of last month's UI.
 */
function HowItWorks() {
  return (
    <section className="how" aria-labelledby="how-title">
      <header className="section-head">
        <p className="hero-eyebrow">How it works</p>
        <h2 id="how-title" className="section-title">
          Watch something good. Keep what you learn.
        </h2>
      </header>

      <div className="how-grid">
        <article className="how-card">
          <div className="how-demo" aria-hidden="true">
            <p className="demo-line">
              We were on a <span className="demo-word">break</span>!
            </p>
            <p className="demo-zh">我们那时候在冷静期！</p>
            <div className="demo-card">
              <div className="demo-card-head">
                <strong>break</strong>
                <span className="phonetic muted small">/breɪk/</span>
              </div>
              <span className="small">n. 暂停；（感情中的）冷静期</span>
            </div>
          </div>
          <h3>Tap any word</h3>
          <p>Meaning, pronunciation and the line it came from — without leaving the scene.</p>
        </article>

        <article className="how-card">
          <div className="how-demo" aria-hidden="true">
            <div className="demo-wave">
              {Array.from({ length: 28 }, (_, i) => (
                <span key={i} style={{ height: `${22 + ((i * 37) % 60)}%` }} className={i >= 9 && i < 19 ? 'on' : ''} />
              ))}
            </div>
            <div className="demo-pills">
              <span>0.5×</span>
              <span className="on">0.75×</span>
              <span>1×</span>
              <span className="demo-loop">↻ Repeat</span>
            </div>
          </div>
          <h3>Loop the hard part</h3>
          <p>Replay one sentence, slow it down, or pause at every full stop until it lands.</p>
        </article>

        <article className="how-card">
          <div className="how-demo" aria-hidden="true">
            <p className="demo-line">
              We were on a <span className="demo-blank">_____</span>!
            </p>
            <div className="demo-grades">
              <span className="bad">Again</span>
              <span className="warn">Hard</span>
              <span className="ok">Good</span>
            </div>
            <p className="demo-due muted small">Next review in 3 days</p>
          </div>
          <h3>It comes back</h3>
          <p>Saved words return as spaced review, cut from the very clip you met them in.</p>
        </article>
      </div>
    </section>
  )
}

/** The shows as posters — one tile each instead of one shelf each. */
function ShowTiles({ shows }: { shows: { show: Show; lessons: LessonSummary[] }[] }) {
  const named = shows.filter(({ show }) => show.key !== 'more')
  return (
    <section className="shows" aria-labelledby="shows-title">
      <header className="section-head">
        <h2 id="shows-title" className="section-title small">
          Pick a show
        </h2>
        <Link to="/library" className="shelf-all">
          Browse all clips
        </Link>
      </header>
      <div className="show-grid">
        {named.map(({ show, lessons }) => {
          // The longest clip tends to have the best still.
          const cover = [...lessons].sort((a, b) => b.duration_ms - a.duration_ms)[0]
          const still = thumbnailUrl(cover?.youtube_id ?? null)
          return (
            <Link key={show.key} to={`/library?show=${show.key}`} className="show-tile">
              <span
                className="show-tile-still"
                style={still ? { backgroundImage: `url(${still})` } : undefined}
                aria-hidden="true"
              />
              <span className="show-tile-body">
                <strong>{show.label}</strong>
                <span className="small">
                  {lessons.length} {lessons.length === 1 ? 'clip' : 'clips'}
                </span>
              </span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}

function ClosingCta({ lesson }: { lesson: LessonSummary | null }) {
  return (
    <section className="closing">
      <h2 className="section-title">Your first word takes ten seconds.</h2>
      <p className="muted">Open a scene, tap anything you don't know. No account until you want to keep it.</p>
      <div className="hero-actions">
        {lesson && (
          <Link to={`/reader/${lesson.id}`} className="btn-hero">
            ▶ Try a lesson
          </Link>
        )}
        <Link to="/login" state={{ mode: 'register' }} className="btn-hero ghost">
          Sign up free
        </Link>
      </div>
    </section>
  )
}

function ShelfSkeleton() {
  return (
    <div className="shelf" aria-hidden="true">
      <div className="shelf-head">
        <div className="skeleton-line" style={{ width: '9rem' }} />
      </div>
      <div className="shelf-row">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="lesson-card skeleton">
            <div className="thumb" />
            <div className="lesson-card-body">
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
