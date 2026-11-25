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
  joined: number
  ready: boolean
  revision: number
  phase: 'roll' | 'move' | 'won'
  die: number
  legal: number[]
  message: string
  pawns: (Pawn & { step: number })[]
}

const base = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function request<T>(path: string, token?: string, body?: object): Promise<T> {
  const headers = new Headers()
  if (token) headers.set('Authorization', 'Bearer ' + token)
  if (body) headers.set('Content-Type', 'application/json')
  const response = await fetch(base + path, {
    method: body ? 'POST' : 'GET', headers, body: JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new ApiError(response.status, typeof error.detail === 'string' ? error.detail : 'Request failed. Please retry.')
  }
  return response.json()
}
