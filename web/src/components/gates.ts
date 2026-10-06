// The copy for each walled route, kept in one place so the promises stay
// consistent with each other — and with what the product actually does.
//
// Separate from SignUpGate.tsx only because a file that exports both a
// component and a constant loses fast refresh.
import type { GateCopy } from './SignUpGate'

export const GATES: Record<'vocab' | 'review', GateCopy> = {
  vocab: {
    title: 'Your word list lives in your account',
    sub: 'Save a word from any clip and it follows you — to the next show, to your phone, to tomorrow.',
    points: [
      'Every word keeps the line and the video you met it in',
      'Saved words are tinted in every transcript you open afterwards',
      'One tap from a word back to the second it was spoken',
    ],
  },
  review: {
    title: 'Review turns saved words into recall',
    sub: 'Spaced repetition on an SM-2 schedule, built from the sentences you actually watched.',
    points: [
      'Cards are cut from the real clip, not a stock example sentence',
      'Words you find hard come back sooner; ones you know go quiet',
      'A daily cap, so it stays a habit and not a backlog',
    ],
  },
}
