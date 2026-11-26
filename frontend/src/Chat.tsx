import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import type { ChatEvent, Match } from './api'
import { EMOTE, EMOTES, QUICK_PHRASES, seatName, type Allowance, type ChatPrefs } from './emotes'
import type { PawnColor } from './types'
import './Chat.css'

function Line({ game, event }: { game: Match; event: ChatEvent }) {
  const who = seatName(game, event.seat)
  if (event.kind === 'chat') return <li data-seat={event.seat}><strong>{who}</strong> <span>{event.body}</span></li>
  const emote = EMOTE[event.body]
  if (!emote) return null
  const target = event.target && seatName(game, event.target)
  return <li data-seat={event.seat} className="emote-line">
    <strong>{who}</strong>{' '}
    {emote.kind === 'throw' && target ? <>{emote.verb} <strong>{target}</strong> {emote.emoji}</>
      : <>{emote.emoji} {emote.label}{target && <> → <strong>{target}</strong></>}</>}
  </li>
}

export default function ChatPanel({ game, events, prefs, setPrefs, muted, toggleMute, open, setOpen, unread,
  sendChat, sendEmote, chat, emote }: {
  game: Match; events: ChatEvent[]; prefs: ChatPrefs; setPrefs: (prefs: ChatPrefs) => void
  muted: Set<PawnColor>; toggleMute: (seat: PawnColor) => void
  open: boolean; setOpen: (open: boolean) => void; unread: number
  sendChat: (text: string) => Promise<void>; sendEmote: (id: string) => Promise<void>
  chat: Allowance; emote: Allowance
}) {
  const [text, setText] = useState('')
  const [settings, setSettings] = useState(false)
  const [error, setError] = useState('')
  const log = useRef<HTMLUListElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const visible = events.filter(e => !muted.has(e.seat) && (e.kind === 'chat' ? prefs.chat : prefs.emotes))
  useLayoutEffect(() => {
    const list = log.current
    if (list) list.scrollTop = list.scrollHeight
  }, [visible.length, open])
  useEffect(() => {
    if (!open) return
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open, setOpen])
  async function say(message: string) {
    setError('')
    try { await sendChat(message); return true } catch (e) { setError((e as Error).message); return false }
  }
  async function submit(e: FormEvent) {
    e.preventDefault()
    const message = text
    if (!message.trim()) return
    // Clear at once so the next message can be typed while this one sends; restore it only on failure.
    setText('')
    input.current?.focus()
    if (!await say(message)) setText(current => current || message)
  }
  const others = game.seated.filter(c => c !== game.seat && !game.out?.includes(c))
  const label = unread ? `Open chat, ${unread} new` : 'Open chat'
  return <aside className="chat" data-open={open} aria-label="Game chat">
    <button type="button" className="chat-toggle" aria-expanded={open} aria-controls="chat-panel"
      aria-label={open ? 'Close chat' : label} title={open ? 'Close chat' : label} onClick={() => setOpen(!open)}>
      <span aria-hidden="true">💬</span>{!open && unread > 0 && <span className="chat-badge">{unread > 9 ? '9+' : unread}</span>}
    </button>
    {open && <div className="chat-backdrop" onClick={() => setOpen(false)} />}
    <section id="chat-panel" className="chat-body" hidden={!open}>
      <header className="chat-head">
        <h2>Chat</h2>
        <button type="button" className="quiet" aria-label="Chat settings" aria-expanded={settings}
          onClick={() => setSettings(!settings)}>⚙︎</button>
        <button type="button" className="quiet" aria-label="Close chat" onClick={() => setOpen(false)}>✕</button>
      </header>
      {settings && <div className="chat-settings">
        <label className="preference">Show chat messages
          <input type="checkbox" checked={prefs.chat} onChange={e => setPrefs({ ...prefs, chat: e.target.checked })} /></label>
        <label className="preference">Show emotes
          <input type="checkbox" checked={prefs.emotes} onChange={e => setPrefs({ ...prefs, emotes: e.target.checked })} /></label>
        {others.map(seat => <label key={seat} className="preference" data-seat={seat}>Mute {seatName(game, seat)}
          <input type="checkbox" checked={muted.has(seat)} onChange={() => toggleMute(seat)} /></label>)}
      </div>}
      <ul className="chat-log" role="log" aria-live="polite" aria-label="Messages" ref={log}>
        {visible.length === 0 && <li className="chat-empty">{prefs.chat ? 'Say hi, or tap a player’s picture to send an emote.' : 'Chat messages are hidden.'}</li>}
        {visible.map(event => <Line key={event.id} game={game} event={event} />)}
      </ul>
      <div className="quick-phrases" aria-label="Quick messages">
        {QUICK_PHRASES.map(phrase => <button key={phrase} type="button" disabled={!chat.left} onClick={() => void say(phrase)}>{phrase}</button>)}
      </div>
      <div className="quick-emotes" role="group" aria-label="Emotes">
        {EMOTES.filter(e => e.kind === 'reaction').map(e =>
          <button key={e.id} type="button" title={e.label} aria-label={e.label} disabled={!emote.left || !prefs.emotes}
            onClick={async () => { setError(''); try { await sendEmote(e.id) } catch (err) { setError((err as Error).message) } }}>{e.emoji}</button>)}
      </div>
      <p className="chat-hint">{emote.left ? `${emote.left} emote${emote.left === 1 ? '' : 's'} left · tap a player’s picture to throw one`
        : `More emotes in ${emote.wait}s`}</p>
      <form className="chat-input" onSubmit={submit}>
        <input ref={input} value={text} maxLength={200} placeholder={chat.left ? 'Message' : `Wait ${chat.wait}s`}
          aria-label="Message" enterKeyHint="send" autoComplete="off" onChange={e => setText(e.target.value)} />
        <button className="primary" disabled={!text.trim() || !chat.left}>Send</button>
      </form>
      {error && <p role="alert" className="chat-error">{error}</p>}
    </section>
  </aside>
}
