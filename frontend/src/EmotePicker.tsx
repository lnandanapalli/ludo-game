import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Match } from './api'
import { EMOTES, portraitOf, seatName, type Allowance } from './emotes'
import type { PawnColor } from './types'

/** Opened from a player's picture: throws for other players, reactions for anyone, and muting. */
export default function EmotePicker({ game, seat, muted, toggleMute, emote, send, close }: {
  game: Match; seat: PawnColor; muted: boolean; toggleMute: () => void; emote: Allowance
  send: (id: string, target: PawnColor | null) => Promise<void>; close: () => void
}) {
  const panel = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const self = seat === game.seat
  useLayoutEffect(() => {
    // Anchor to the whole player card so the name stays visible.
    const box = (portraitOf(seat)?.closest('.seat-card') ?? portraitOf(seat))?.getBoundingClientRect()
    const node = panel.current
    if (!box || !node) return
    const width = node.offsetWidth, height = node.offsetHeight
    const left = Math.min(innerWidth - width - 8, Math.max(8, box.left + box.width / 2 - width / 2))
    const below = box.bottom + 8 + height <= innerHeight
    node.style.left = left + 'px'
    node.style.top = (below ? box.bottom + 8 : Math.max(8, box.top - height - 8)) + 'px'
    node.querySelector('button')?.focus()
  }, [seat])
  useEffect(() => {
    const outside = (e: PointerEvent) => { if (!panel.current?.contains(e.target as Node)) close() }
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('pointerdown', outside)
    window.addEventListener('keydown', escape)
    return () => { window.removeEventListener('pointerdown', outside); window.removeEventListener('keydown', escape) }
  }, [close])
  const choices = EMOTES.filter(e => !self || e.kind === 'reaction')
  return <div ref={panel} className="emote-picker" role="dialog" aria-label={self ? 'Send a reaction' : `Send an emote to ${seatName(game, seat)}`}>
    <p className="emote-picker-title">{self ? 'React' : <>Send to <strong>{seatName(game, seat)}</strong></>}</p>
    <div className="emote-grid">
      {choices.map(e => <button key={e.id} type="button" title={e.label} aria-label={e.label} disabled={!emote.left || sending}
        onClick={async () => {
          setSending(true)  // One emote per tap, even if the reply is slow.
          try { await send(e.id, self ? null : seat); close() }
          catch (err) { setError((err as Error).message); setSending(false) }
        }}><span aria-hidden="true">{e.emoji}</span><small>{e.label}</small></button>)}
    </div>
    <p className="chat-hint">{emote.left ? `${emote.left} emote${emote.left === 1 ? '' : 's'} left` : `More emotes in ${emote.wait}s`}</p>
    {error && <p role="alert" className="chat-error">{error}</p>}
    {!self && <label className="preference">Mute {seatName(game, seat)}
      <input type="checkbox" checked={muted} onChange={toggleMute} /></label>}
  </div>
}
