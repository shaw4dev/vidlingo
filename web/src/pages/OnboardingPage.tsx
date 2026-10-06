// Two questions, asked once, right after the account exists.
//
// Both answers do something visible before the next screen loads — the level
// reorders the explore shelves, the goal becomes the number on the review
// page. That is the whole bar for an onboarding question: if the answer does
// not change the next screen, it is a form, and nobody signed up to fill in a
// form.
//
// Skipping is a real option and says so. An onboarding you cannot leave is the
// fastest way to lose someone who has already given you an email address.
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { DIFFICULTIES, type Difficulty } from '../features/library/useLessons'
import { GOALS, useLearnerPrefs, useSavePrefs } from '../features/prefs/useLearnerPrefs'

// Keyed by difficulty rather than listed, so a fourth level added to the
// corpus fails to compile here instead of quietly going unoffered.
const LEVELS: Record<Difficulty, { label: string; hint: string }> = {
  easy: {
    label: 'Getting comfortable',
    hint: 'Short lines, everyday words, one idea at a time.',
  },
  medium: {
    label: 'Pretty confident',
    hint: 'Natural pace, idiom and jokes, the occasional rewind.',
  },
  hard: { label: 'Chasing fluency', hint: 'Fast, unscripted, overlapping speech. No mercy.' },
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const location = useLocation()
  // Sign-up may have interrupted a journey — a click on Review, say. Finish
  // onboarding by resuming it, not by dumping her on the home page.
  const next = (location.state as { from?: string } | null)?.from ?? '/'
  const { user } = useAuth()
  const prefs = useLearnerPrefs()
  const savePrefs = useSavePrefs()

  const [step, setStep] = useState<0 | 1>(0)
  const [level, setLevel] = useState<Difficulty>(prefs.level)
  const [goal, setGoal] = useState<number>(prefs.dailyGoal)

  function finish(saveAnswers: boolean) {
    // Skipping still stamps onboardedAt: the question has been asked, and
    // asking it again on the next visit is how a product nags.
    savePrefs(
      saveAnswers ? { level, dailyGoal: goal, onboardedAt: Date.now() } : { onboardedAt: Date.now() },
    )
    navigate(next, { replace: true })
  }

  return (
    <div className="auth-page">
      <main className="auth-card onboard">
        <div className="onboard-steps" aria-hidden="true">
          <span className={step === 0 ? 'on' : ''} />
          <span className={step === 1 ? 'on' : ''} />
        </div>

        {step === 0 ? (
          <>
            <h1 className="auth-title">
              {user ? `Welcome, ${user.username}.` : 'Welcome.'} How is your English right now?
            </h1>
            <p className="auth-sub">
              This only decides which shelf we put at the top. You can watch anything, any time.
            </p>
            <div className="choice-list">
              {DIFFICULTIES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={level === value ? 'choice on' : 'choice'}
                  onClick={() => setLevel(value)}
                >
                  <strong>{LEVELS[value].label}</strong>
                  <span className="muted small">{LEVELS[value].hint}</span>
                </button>
              ))}
            </div>
            <button className="btn-primary" onClick={() => setStep(1)}>
              Continue
            </button>
          </>
        ) : (
          <>
            <h1 className="auth-title">How many words a day?</h1>
            <p className="auth-sub">
              Your review queue stops at this number, so a busy week never turns into a backlog
              of four hundred cards.
            </p>
            <div className="choice-row">
              {GOALS.map((g) => (
                <button
                  key={g}
                  type="button"
                  className={goal === g ? 'choice-pill on' : 'choice-pill'}
                  onClick={() => setGoal(g)}
                >
                  <strong>{g}</strong>
                  <span className="muted small">a day</span>
                </button>
              ))}
            </div>
            <button className="btn-primary" onClick={() => finish(true)}>
              Start watching
            </button>
            <button className="btn-quiet onboard-back" onClick={() => setStep(0)}>
              ← Back
            </button>
          </>
        )}

        <button className="link onboard-skip" onClick={() => finish(false)}>
          Skip — just show me the library
        </button>
      </main>
    </div>
  )
}
