import type { Pawn, PawnColor } from './types'

export interface Session { room: string; token: string; mode?: Match['mode'] }
export interface Profile { name: string; avatar: string }
export interface Match {
  last_move?: { roll: number; pawn: string; path: [number, number][] } | null
  started_at?: number | null
  can_end: boolean
  substitutes?: boolean
  computers?: PawnColor[]
  profiles: Record<string, Profile>
  roll_number: number
  roller: PawnColor | null
  room: string
  mode: 'local' | 'online'
  current: PawnColor
  seat: PawnColor
  colors: PawnColor[]
  out: PawnColor[]
  joined: number
  ready: boolean
  revision: number
  phase: 'roll' | 'move' | 'won'
  die: number
  legal: number[]
  message: string
  pawns: (Pawn & { step: number })[]
  presence: Partial<Record<PawnColor, 'online' | 'offline' | 'left' | 'computer'>>
  turn_seconds: number
  turn_remaining: number | null
}

export interface Account {
  username: string
  profile: Profile
  stats: { games: number; wins: number }
  games: { room: string; color: PawnColor; started_at: number | null; players: string[] }[]
}

const base = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
const accountKey = 'ludo-account'

export function accountToken() {
  try { return localStorage.getItem(accountKey) || '' } catch { return '' }
}

export function setAccountToken(token: string | null) {
  try {
    if (token) localStorage.setItem(accountKey, token)
    else localStorage.removeItem(accountKey)
  } catch { /* Storage is optional; the sign-in lasts for this page. */ }
  window.dispatchEvent(new Event('ludo-account'))
}

export class ApiError extends Error {
  status: number
  retryAfter: number
  constructor(status: number, message: string, retryAfter = 0) {
    super(message); this.status = status; this.retryAfter = retryAfter
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

export async function request<T>(path: string, token?: string, body?: object, method?: Method): Promise<T> {
  const headers = new Headers()
  if (token) headers.set('Authorization', 'Bearer ' + token)
  const account = accountToken()
  if (account) headers.set('X-Account-Token', account)
  if (body) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(base + path, {
      method: method ?? (body ? 'POST' : 'GET'), headers, body: body && JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Connection problem. Check your network and try again.')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const detail = typeof error.detail === 'string' ? error.detail : 'Request failed. Please retry.'
    // An expired sign-in should not block play: forget it and let the player continue as a guest.
    if (response.status === 401 && account && detail.startsWith('Your sign-in expired')) setAccountToken(null)
    throw new ApiError(response.status, detail, Number(response.headers.get('Retry-After')) || 0)
  }
  return response.json()
}

/** The saved seat no longer exists or no longer belongs to this browser. */
export function unavailable(e: unknown) {
  return e instanceof ApiError && [403, 404, 410].includes(e.status)
    || e instanceof ApiError && e.status === 401 && !e.message.startsWith('Your sign-in expired')
}
