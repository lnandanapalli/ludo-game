import type { Match } from './api'
import type { PawnColor } from './types'

export type Flight = 'wiggle' | 'arc' | 'line' | 'float'
export interface Emote {
  id: string
  emoji: string
  label: string
  /** Reactions pop up over the sender; throws fly to the chosen player. */
  kind: 'reaction' | 'throw'
  flight?: Flight
  /** Turn the emoji to face its direction of travel (and the angle it is drawn at). */
  aim?: number
  /** Little pieces that burst out where a throw lands. */
  impact?: string[]
  /** Chat-log wording: "{sender} {verb} {target}". */
  verb?: string
}

export const EMOTES: Emote[] = [
  { id: 'ooo', emoji: '😮', label: 'Oooo!', kind: 'reaction' },
  { id: 'howzat', emoji: '🏏', label: "How's that?", kind: 'reaction' },
  { id: 'haha', emoji: '😂', label: 'Haha!', kind: 'reaction' },
  { id: 'clap', emoji: '👏', label: 'Well played!', kind: 'reaction' },
  { id: 'cool', emoji: '😎', label: 'Too easy', kind: 'reaction' },
  { id: 'cry', emoji: '😭', label: 'Nooo!', kind: 'reaction' },
  { id: 'thinking', emoji: '🤔', label: 'Hmm…', kind: 'reaction' },
  { id: 'goodluck', emoji: '🍀', label: 'Good luck!', kind: 'reaction' },
  { id: 'snake', emoji: '🐍', label: 'Snake', kind: 'throw', flight: 'wiggle', aim: 180, impact: ['💫', '💫'], verb: 'sent a sneaky snake to' },
  { id: 'rocket', emoji: '🚀', label: 'Rocket', kind: 'throw', flight: 'line', aim: -45, impact: ['💥', '✨', '✨'], verb: 'launched a rocket at' },
  { id: 'tomato', emoji: '🍅', label: 'Tomato', kind: 'throw', flight: 'arc', impact: ['💦', '💦', '🍅'], verb: 'tossed a tomato at' },
  { id: 'rose', emoji: '🌹', label: 'Rose', kind: 'throw', flight: 'float', impact: ['✨', '✨', '✨'], verb: 'gave a rose to' },
  { id: 'heart', emoji: '❤️', label: 'Love', kind: 'throw', flight: 'float', impact: ['💕', '💖', '💕'], verb: 'sent love to' },
  { id: 'party', emoji: '🎉', label: 'Party', kind: 'throw', flight: 'arc', impact: ['🎊', '✨', '🎊'], verb: 'threw a party for' },
]
export const EMOTE = Object.fromEntries(EMOTES.map(e => [e.id, e])) as Record<string, Emote>

export const QUICK_PHRASES = ['Good luck!', 'Well played!', 'Nice move!', 'Oops!', 'So close!', 'Hurry up! ⏳', 'GG 🤝']

/** Mirrors the server's allowances so buttons can show what is left before a request is refused. */
export const ALLOWANCE = { emote: { burst: 3, every: 20 }, chat: { burst: 6, every: 4 } } as const

export interface ChatPrefs { chat: boolean; emotes: boolean }
const PREFS = 'ludo-chat'

export function loadPrefs(): ChatPrefs {
  try { return { chat: true, emotes: true, ...JSON.parse(localStorage.getItem(PREFS) || '{}') } }
  catch { return { chat: true, emotes: true } }
}

export function savePrefs(prefs: ChatPrefs) {
  try { localStorage.setItem(PREFS, JSON.stringify(prefs)) } catch { /* Preferences last for this page. */ }
}

/** Token bucket matching the server's, refilled continuously. */
export function remaining(sent: number[], kind: keyof typeof ALLOWANCE, now: number) {
  const { burst, every } = ALLOWANCE[kind]
  let tokens: number = burst
  let last = 0
  for (const at of sent) {
    tokens = Math.min(burst, tokens + (at - last) / 1000 / every)
    tokens -= 1
    last = at
  }
  tokens = Math.min(burst, tokens + (now - last) / 1000 / every)
  return { left: Math.floor(tokens), wait: tokens >= 1 ? 0 : Math.ceil((1 - tokens) * every) }
}

export const portraitOf = (seat: PawnColor) => document.querySelector<HTMLElement>(`.seat-card[data-seat="${seat}"] .portrait`)

export interface Allowance { left: number; wait: number }

export function seatName(game: Match, seat: PawnColor | null) {
  if (!seat) return ''
  if (seat === game.seat) return 'You'
  return game.profiles[seat]?.name?.trim() || seat[0].toUpperCase() + seat.slice(1)
}
