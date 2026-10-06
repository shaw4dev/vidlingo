// Which show a clip belongs to, and what to call the clip once the show's name
// has been taken out of its title.
//
// The corpus has a `source` field, but it is the *uploader*, not the show: all
// twenty-one Grosse Pointe Garden Society clips say "NBC". Grouping by source
// therefore produces a shelf called NBC containing one series, which is how a
// file listing looks, not how a library looks. The titles do carry the show —
// "… | Grosse Pointe Garden Society | NBC", "… - The Office US" — but in four
// different shapes, and one clip carries it in neither (the Fallon round).
//
// So: an explicit table. Thirty-nine clips is a catalogue, not a stream, and
// what belongs on a shelf is an editorial call anyway. Each entry owns both
// halves of the problem — how to recognise the show, and how its name appears
// in titles so it can be stripped back off.
import type { LessonSummary } from '../../lib/api'

export interface Show {
  /** Stable id, used as a React key and in shelf ordering. */
  key: string
  /** What the shelf header says. */
  label: string
  /** One line for the shelf subhead — the reason to watch this one. */
  blurb: string
}

interface ShowRule extends Show {
  /** Matched against `${title} | ${source}`. */
  match: RegExp
  /** Title fragments to strip once the show is known. */
  strip: RegExp[]
}

const RULES: ShowRule[] = [
  {
    key: 'friends',
    label: 'Friends',
    blurb: 'Fast, idiomatic, and short — the classic first sitcom to study with.',
    match: /\bFriends\b/i,
    strip: [/\s*\|\s*Friends\s*$/i],
  },
  {
    key: 'the-office',
    label: 'The Office',
    blurb: 'Deadpan workplace English, heavy on sarcasm and small talk.',
    match: /\bThe Office\b/i,
    strip: [/\s*[-|]\s*The Office(?:\s+US)?\s*$/i],
  },
  {
    key: 'grosse-pointe',
    label: 'Grosse Pointe Garden Society',
    blurb: 'Contemporary drama dialogue — full sentences, slower than sitcom.',
    match: /\bGrosse Pointe Garden Society\b/i,
    strip: [/\s*\|\s*Grosse Pointe Garden Society\s*\|\s*NBC\s*$/i, /\s*\|\s*NBC\s*$/i],
  },
  {
    key: 'ted',
    label: 'TED Talks',
    blurb: 'Prepared, structured speech — the register exams and interviews test.',
    match: /\|\s*TED\b|\bTED\b/,
    strip: [/\s*\|\s*TED\s*$/i],
  },
  {
    key: 'tonight-show',
    label: 'The Tonight Show',
    blurb: 'Unscripted celebrity chat: interruptions, laughter, real speed.',
    match: /Jimmy Fallon|Tonight Show/i,
    strip: [/\s*\|\s*The Tonight Show.*$/i],
  },
]

/** All the show rules read — so a feed clip, which is not a lesson, can ask too. */
type Titled = Pick<LessonSummary, 'title' | 'source'>

const FALLBACK: Show = {
  key: 'more',
  label: 'More from the library',
  blurb: 'Everything else in the corpus.',
}

function ruleFor(lesson: Titled): ShowRule | null {
  const hay = `${lesson.title} | ${lesson.source ?? ''}`
  return RULES.find((r) => r.match.test(hay)) ?? null
}

export function showOf(lesson: Titled): Show {
  const rule = ruleFor(lesson)
  if (!rule) return FALLBACK
  const { key, label, blurb } = rule
  return { key, label, blurb }
}

/** The clip's own title, with the show and network furniture removed.
 *
 *  "Jim PRANKS Andy | The Office US" is three quarters shelf header when it
 *  sits on a shelf headed "The Office". */
export function clipTitle(lesson: Titled): string {
  const rule = ruleFor(lesson)
  let t = lesson.title
  for (const re of rule?.strip ?? []) t = t.replace(re, '')
  return t.trim() || lesson.title
}

/** Show order on the explore page: biggest catalogue first, fallback last. */
export function showsByCatalogue(lessons: LessonSummary[]): { show: Show; lessons: LessonSummary[] }[] {
  const groups = new Map<string, { show: Show; lessons: LessonSummary[] }>()
  for (const lesson of lessons) {
    const show = showOf(lesson)
    const group = groups.get(show.key) ?? { show, lessons: [] }
    group.lessons.push(lesson)
    groups.set(show.key, group)
  }
  return [...groups.values()].sort((a, b) => {
    if (a.show.key === FALLBACK.key) return 1
    if (b.show.key === FALLBACK.key) return -1
    return b.lessons.length - a.lessons.length
  })
}
