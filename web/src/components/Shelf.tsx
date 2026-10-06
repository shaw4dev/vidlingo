// A horizontal row of clips, with arrows.
//
// The row is a real scroll container, not a transform carousel: the wheel, a
// trackpad swipe, a touch drag and Tab-to-focus all work for free, and the
// arrows just call scrollBy. A hand-rolled carousel would have to reimplement
// each of those and would still break the focus ring.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

export function Shelf({
  title,
  blurb,
  seeAllTo,
  children,
}: {
  title: string
  blurb?: string
  seeAllTo?: string
  children: ReactNode
}) {
  const rowRef = useRef<HTMLDivElement>(null)
  // Arrows appear only where there is somewhere to go — a dead arrow on a
  // three-card shelf is worse than no arrow.
  const [atStart, setAtStart] = useState(true)
  const [atEnd, setAtEnd] = useState(true)

  const measure = useCallback(() => {
    const el = rowRef.current
    if (!el) return
    const max = el.scrollWidth - el.clientWidth
    setAtStart(el.scrollLeft <= 1)
    setAtEnd(el.scrollLeft >= max - 1)
  }, [])

  useEffect(() => {
    measure()
    const el = rowRef.current
    if (!el) return
    // Cards arrive with the lesson list, and thumbnails change the width as
    // they load; a one-shot measure would leave the arrows wrong.
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [measure, children])

  const nudge = (dir: 1 | -1) => {
    const el = rowRef.current
    if (!el) return
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: 'smooth' })
  }

  return (
    <section className="shelf">
      <header className="shelf-head">
        <div>
          <h2 className="shelf-title">{title}</h2>
          {blurb && <p className="shelf-blurb muted small">{blurb}</p>}
        </div>
        <span className="spacer" />
        {seeAllTo && (
          <Link to={seeAllTo} className="shelf-all">
            See all
          </Link>
        )}
        <div className="shelf-arrows">
          <button
            className="shelf-arrow"
            onClick={() => nudge(-1)}
            disabled={atStart}
            aria-label={`Scroll ${title} left`}
          >
            ‹
          </button>
          <button
            className="shelf-arrow"
            onClick={() => nudge(1)}
            disabled={atEnd}
            aria-label={`Scroll ${title} right`}
          >
            ›
          </button>
        </div>
      </header>
      <div className="shelf-row" ref={rowRef} onScroll={measure}>
        {children}
      </div>
    </section>
  )
}
