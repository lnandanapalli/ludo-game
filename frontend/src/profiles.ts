import type { Profile } from './api'

export const portraits: Record<string, string> = { fox: '🦊', panda: '🐼', tiger: '🐯', frog: '🐸', owl: '🦉', koala: '🐨' }
export function defaultProfile(color: string): Profile {
  const avatars: Record<string, string> = { red: 'fox', green: 'frog', yellow: 'tiger', blue: 'koala' }
  return { name: '', avatar: avatars[color] || 'panda' }
}

