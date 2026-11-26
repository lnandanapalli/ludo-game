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

/** `landing` is how many seconds until an animated pawn reaches its square. */
let noise: AudioBuffer | undefined

/** Dice clattering on a board: filtered noise clicks that slow down. */
function rattle() {
  if (!enabled || !context || !output || context.state !== 'running') return
  if (!noise) {
    noise = context.createBuffer(1, Math.floor(context.sampleRate * 0.06), context.sampleRate)
    const data = noise.getChannelData(0)
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 2
  }
  const start = context.currentTime
  const hits = [0, 0.05, 0.1, 0.16, 0.23, 0.3, 0.38, 0.47]
  hits.forEach((offset, i) => {
    const at = start + offset + Math.random() * 0.015
    const source = context!.createBufferSource()
    source.buffer = noise!
    source.playbackRate.value = 0.75 + Math.random() * 0.5
    const filter = context!.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.value = 1600 + Math.random() * 2400
    filter.Q.value = 3.5
    const gain = context!.createGain()
    const peak = 0.55 * (1 - (i / hits.length) * 0.65)
    gain.gain.setValueAtTime(0.0001, at)
    gain.gain.exponentialRampToValueAtTime(peak, at + 0.002)
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.055)
    source.connect(filter).connect(gain).connect(output!)
    source.onended = () => { source.disconnect(); filter.disconnect(); gain.disconnect() }
    source.start(at)
    source.stop(at + 0.07)
  })
}

export function playChanges(old: Match, next: Match, landing?: number) {
  const rolled = next.roll_number > old.roll_number
  if (rolled) rattle()
  const delay = landing ?? (rolled ? 0.6 : 0)
  const changes = next.pawns.filter(p => old.pawns.find(previous => previous.id === p.id)?.step !== p.step)
  if (next.phase === 'won' && old.phase !== 'won') {
    notes([392, 494, 587, 784], 0.12, 0.22, delay)
    notes([523, 659, 784, 1047], 0.1, 0.3, delay + 0.55)
  }
  else if (changes.some(p => p.step === -1)) notes([523, 330, 196], 0.07, 0.12, delay)
  else if (changes.length) notes([440, 554], 0.045, 0.08, delay)
}

/** A soft chime for friendly emotes, a quick pop for throws landing. */
export function emoteSound(soft: boolean) {
  if (soft) notes([784, 1047], 0.07, 0.12)
  else notes([330, 247], 0.04, 0.09)
}

/** A quiet tick for an incoming chat message. */
export function chatSound() {
  notes([1175], 0, 0.05)
}
