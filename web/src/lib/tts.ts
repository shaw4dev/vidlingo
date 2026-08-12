// Pronunciation playback for the word card (T13).
//
// Two sources, in order of preference:
//   1. The dictionary's own recording (a real human voice) when it has one.
//   2. The browser's SpeechSynthesis — free, offline, everywhere, but robotic.
//
// Audio elements are created per call and left to GC; a word card plays one
// short clip at a time, so pooling would be complexity for nothing.

let cachedVoice: SpeechSynthesisVoice | null | undefined

function englishVoice(): SpeechSynthesisVoice | null {
  if (cachedVoice !== undefined) return cachedVoice
  const voices = window.speechSynthesis?.getVoices?.() ?? []
  // Voices load asynchronously in some browsers — don't cache an empty list.
  if (voices.length === 0) return null
  cachedVoice =
    voices.find((v) => v.lang === 'en-US') ??
    voices.find((v) => v.lang?.startsWith('en')) ??
    null
  return cachedVoice
}

export function canSpeak(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/** Speak `text` with the browser's synthesizer. No-op where unsupported. */
export function speak(text: string) {
  if (!canSpeak()) return
  window.speechSynthesis.cancel() // stop whatever is mid-word
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = 0.9 // a touch slow: this is for a learner
  const voice = englishVoice()
  if (voice) utterance.voice = voice
  window.speechSynthesis.speak(utterance)
}

/**
 * Play a recorded pronunciation, falling back to synthesis if the audio fails
 * (dead CDN links are common in free dictionary data).
 */
export function pronounce(text: string, audioUrl?: string | null) {
  if (!audioUrl) {
    speak(text)
    return
  }
  const audio = new Audio(audioUrl)
  audio.play().catch(() => speak(text))
  audio.addEventListener('error', () => speak(text), { once: true })
}
