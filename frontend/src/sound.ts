import type { Match } from './api'

const key = 'ludo-sound'
let enabled = true
try { enabled = localStorage.getItem(key) !== 'off' } catch { /* Storage is optional. */ }
let context: AudioContext | undefined
let output: GainNode | undefined

export function soundEnabled() { return enabled }

export function unlockSound() {
  if (!enabled || !window.AudioContext) return
  if (!context) {
    context = new AudioContext()
    output = context.createGain()
    output.connect(context.destination)
  }
  if (context.state === 'suspended') void context.resume().catch(() => {})
}

export function setSound(value: boolean) {
  enabled = value
  try { localStorage.setItem(key, value ? 'on' : 'off') } catch { /* Keep the session preference. */ }
  if (value) unlockSound()
  if (output) output.gain.value = value ? 1 : 0
}

function notes(pitches: number[], spacing: number, duration: number, delay = 0) {
  if (!enabled || !context || !output || context.state !== 'running') return
  const start = context.currentTime + delay
  for (const [i, pitch] of pitches.entries()) {
    const at = start + i * spacing
    const tone = context.createOscillator()
    const envelope = context.createGain()
    tone.type = 'triangle'
    tone.frequency.setValueAtTime(pitch, at)
    tone.frequency.exponentialRampToValueAtTime(pitch * 0.85, at + duration)
    envelope.gain.setValueAtTime(0.001, at)
    envelope.gain.exponentialRampToValueAtTime(0.12, at + 0.005)
    envelope.gain.exponentialRampToValueAtTime(0.001, at + duration)
    tone.connect(envelope).connect(output)
    tone.onended = () => { tone.disconnect(); envelope.disconnect() }
    tone.start(at)
    tone.stop(at + duration)
  }
}

export function playChanges(old: Match, next: Match) {
  const rolled = next.roll_number > old.roll_number
  if (rolled) notes([610, 390, 510, 320], 0.055, 0.04)
  const delay = rolled ? 0.25 : 0
  const changes = next.pawns.filter(p => old.pawns.find(previous => previous.id === p.id)?.step !== p.step)
  if (next.phase === 'won' && old.phase !== 'won') notes([392, 494, 587, 784], 0.12, 0.22, delay)
  else if (changes.some(p => p.step === -1)) notes([523, 330, 196], 0.07, 0.12, delay)
  else if (changes.length) notes([440, 554], 0.045, 0.08, delay)
}
