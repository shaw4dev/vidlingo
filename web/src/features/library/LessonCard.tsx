// One clip, as it appears on a shelf and in the library grid.
//
// Shared so the two surfaces cannot drift: a card that says "Jim PRANKS Andy |
// The Office US" in one place and "Jim PRANKS Andy" in the other looks like
// two different products.
import { Link } from 'react-router-dom'
import type { LessonSummary } from '../../lib/api'
import { clipTitle, showOf } from './shows'
import {
  DIFFICULTY_LABELS,
  formatDuration,
  thumbnailUrl,
  type Difficulty,
} from './useLessons'

export function LessonCard({
  lesson,
  resumeIdx,
  progress,
  showShow = true,
}: {
  lesson: LessonSummary
  /** Sentence to resume at, from the watch history. */
  resumeIdx?: number
  /** 0–1, drawn as a bar across the bottom of the still. */
  progress?: number
  /** Off on a shelf that is already headed with the show's name. */
  showShow?: boolean
}) {
  const thumb = thumbnailUrl(lesson.youtube_id)
  const to = resumeIdx != null ? `/reader/${lesson.id}?s=${resumeIdx}` : `/reader/${lesson.id}`
  const difficulty = lesson.difficulty as Difficulty | null

  return (
    <Link to={to} className="lesson-card">
      <div className="thumb" style={thumb ? { backgroundImage: `url(${thumb})` } : undefined}>
        <span className="thumb-duration">{formatDuration(lesson.duration_ms)}</span>
        <span className="thumb-play" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="20" height="20">
            <polygon points="8,5 20,12 8,19" fill="currentColor" />
          </svg>
        </span>
        {progress != null && progress > 0 && (
          <span className="thumb-progress" aria-hidden="true">
            <span style={{ width: `${Math.round(progress * 100)}%` }} />
          </span>
        )}
      </div>
      <div className="lesson-card-body">
        <div className="lesson-card-title">{clipTitle(lesson)}</div>
        <div className="lesson-card-meta">
          {difficulty && (
            <span className={`level level-${difficulty}`}>
              {DIFFICULTY_LABELS[difficulty] ?? difficulty}
            </span>
          )}
          <span className="muted small">
            {showShow ? showOf(lesson).label : lesson.theme.replace(/_/g, ' ')}
          </span>
        </div>
      </div>
    </Link>
  )
}
