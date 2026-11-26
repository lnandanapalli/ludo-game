import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { PAWN_COLOR_HEX } from './types'
import Board from './Board'
import { ApiError, request, unavailable, type ChatEvent, type Match, type Session } from './api'
import ChatPanel from './Chat'
import EmoteLayer, { type Show } from './EmoteLayer'
import EmotePicker from './EmotePicker'
import { ALLOWANCE, loadPrefs, remaining, savePrefs, type ChatPrefs } from './emotes'
import type { PawnColor } from './types'
import Confetti from './Confetti'
import Die from './Die'
import { Wordmark } from './Nav'
import SoundToggle from './SoundToggle'
import { chatSound, playChanges } from './sound'
import { defaultProfile, portraits } from './profiles'

const POLL_MS = 1800
const WIDE = '(min-width: 1100px)'  // Room beside the board for the chat panel.
const AUTO_MOVE_RESULT_HOLD_MS = 1000
const MOVE_WARNING_SECONDS = 5
function TimerRing({ timer }: { timer: { delay: number; remaining: number; total: number } }) {
  return <svg className="turn-timer" viewBox="0 0 44 44" aria-hidden="true">
    <circle cx="22" cy="22" r="20" pathLength="100" style={{
      animationDuration: timer.remaining + 's', animationDelay: timer.delay + 's',
      '--spent': (1 - timer.remaining / timer.total) * 100,
    } as React.CSSProperties} />
  </svg>
}
const presenceLabels = { offline: 'Offline', left: 'Left', computer: 'CPU' } as const
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const travelDuration = (path: [number, number][]) => reducedMotion() ? 0 : Math.max(250, (path.length - 1) * 165)

// Starts from rest, picks up speed quickly, then slows gradually into the target square and stops
// exactly on it, with no overshoot.
const TRAVEL_EASING = 'cubic-bezier(0.3, 0, 0.15, 1)'

export default function Play({ session, leave, forget }: { session: Session; leave: () => void; forget: (message: string) => void }) {
  const [game, setGame] = useState<Match | null>(null)
  const [travel, setTravel] = useState<{ move: NonNullable<Match['last_move']>; before: Match; die: number; delay: number } | null>(null)
  const traveler = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    if (!travel || !traveler.current) return
    const path = travel.move.path
    // Keyframes sit evenly on each square's centre; one easing over the whole path sets the speed.
    const frames: Keyframe[] = path.map(([row, col], i) => ({
      transform: `translate(${col * 100}%, ${row * 100}%)`, offset: i / (path.length - 1), easing: 'linear',
    }))
    const timing = { duration: travelDuration(path), delay: travel.delay, fill: 'both' as const }
    const movement = traveler.current.animate(frames, { ...timing, easing: TRAVEL_EASING })
    // The pawn lifts slightly while it travels and is set down gently as it arrives.
    const icon = traveler.current.firstElementChild
    const lift = icon?.animate([{ scale: 1 }, { scale: 1.12, offset: 0.15 }, { scale: 1.12, offset: 0.7 }, { scale: 1 }],
      { ...timing, easing: 'ease-out' })
    movement.onfinish = () => setTravel(null)
    return () => { movement.cancel(); lift?.cancel() }
  }, [travel])
  // Chat and emotes (online rooms).
  const [events, setEvents] = useState<ChatEvent[]>([])
  const lastEvent = useRef(0)
  const historyLoaded = useRef(false)
  const [shows, setShows] = useState<Show[]>([])
  const [prefs, setPrefsState] = useState<ChatPrefs>(loadPrefs)
  const setPrefs = useCallback((next: ChatPrefs) => { setPrefsState(next); savePrefs(next) }, [])
  const [muted, setMuted] = useState<Set<PawnColor>>(() => new Set())
  const [chatOpen, setChatOpenState] = useState(() => window.matchMedia(WIDE).matches)
  const [unread, setUnread] = useState(0)
  const setChatOpen = useCallback((open: boolean) => { setChatOpenState(open); if (open) setUnread(0) }, [])
  const [picker, setPicker] = useState<PawnColor | null>(null)
  const [sent, setSent] = useState<{ chat: number[]; emote: number[] }>({ chat: [], emote: [] })
  const [cooldown, setCooldown] = useState({ chat: 0, emote: 0 })
  const [now, setNow] = useState(() => performance.now())
  const live = useRef({ prefs, muted, chatOpen, seat: null as PawnColor | null })
  useEffect(() => { live.current = { prefs, muted, chatOpen, seat: latest.current?.seat ?? null } })
  const receive = useCallback((incoming: ChatEvent[]) => {
    const fresh = incoming.filter(e => e.id > lastEvent.current)
    if (!fresh.length && historyLoaded.current) return
    lastEvent.current = Math.max(lastEvent.current, ...fresh.map(e => e.id))
    setEvents(list => [...list, ...fresh.filter(e => !list.some(old => old.id === e.id))].slice(-200))
    if (!historyLoaded.current) { historyLoaded.current = true; return }  // History: no replays or badges.
    const { prefs, muted, chatOpen, seat } = live.current
    for (const e of fresh) {
      if (e.seat === seat || muted.has(e.seat)) continue
      if (e.kind === 'emote' && prefs.emotes) setShows(list => [...list, { key: e.id, emote: e.body, from: e.seat, to: e.target }])
      if (e.kind === 'chat' && prefs.chat) {
        if (!chatOpen) setUnread(n => n + 1)
        chatSound()
      }
    }
  }, [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [timer, setTimer] = useState<{ revision: number; phase: Match['phase']; delay: number; remaining: number; total: number } | null>(null)
  const [warned, setWarned] = useState<number | null>(null)
  useEffect(() => {
    if (timer?.phase !== 'move') return
    const id = window.setTimeout(() => setWarned(timer.revision),
      Math.max(0, timer.delay + timer.remaining - MOVE_WARNING_SECONDS) * 1000)
    return () => clearTimeout(id)
  }, [timer])
  const latest = useRef<Match | null>(null)
  const [roller, setRoller] = useState<Match['roller']>(null)
  const rolling = roller !== null
  const clickedAt = useRef<number | null>(null)
  const animation = useRef<number | undefined>(undefined)
  const path = '/rooms/' + session.room
  const accept = useCallback((next: Match) => {
    const old = latest.current
    if (old && next.revision < old.revision) return
    // Restart the countdown only when the turn changes, not on every poll.
    setTimer(t => next.turn_remaining === null ? null : t?.revision === next.revision ? t : {
      revision: next.revision, phase: next.phase, total: next.turn_seconds,
      // The server starts the clock after the last roll or move has been animated.
      delay: Math.max(0, next.turn_remaining - next.turn_seconds), remaining: Math.min(next.turn_remaining, next.turn_seconds),
    })
    if (old && next.revision === old.revision) {
      // Same board; only live details such as player presence can differ.
      latest.current = next
      setGame(next)
      return
    }
    let rollDelay = 0
    if (old && next.roll_number > old.roll_number) {
      const now = performance.now()
      rollDelay = Math.max(0, 620 - (now - (clickedAt.current ?? now)))
      clickedAt.current = null
      setRoller(next.roller)
      window.clearTimeout(animation.current)
      animation.current = window.setTimeout(() => setRoller(null), rollDelay)
    }
    const move = next.last_move
    let landing: number | undefined
    if (old && move && move.roll !== old.last_move?.roll) {
      const pawn = old.pawns.find(p => p.id === move.pawn)
      const [row, col] = move.path[0]
      const rolledAndMoved = move.roll === next.roll_number && next.roll_number > old.roll_number
      const delay = rollDelay + (rolledAndMoved ? AUTO_MOVE_RESULT_HOLD_MS : 0)
      const travels = pawn?.row === row && pawn.col === col
      setTravel(travels ? { move, before: old, die: next.die, delay } : null)
      // Land the move's sound with the pawn rather than when the update arrives.
      if (travels) landing = (delay + travelDuration(move.path)) / 1000
    }
    if (old) playChanges(old, next, landing)
    latest.current = next
    setGame(next)
  }, [])
  useEffect(() => {
    let active = true
    let timer: number
    let failures = 0
    async function refresh() {
      let wait = POLL_MS
      try {
        const next = await request<Match>(path + '?events_after=' + lastEvent.current, session.token)
        failures = 0
        if (active) { accept(next); if (next.events) receive(next.events); setError('') }
      } catch (e) {
        if (active && unavailable(e)) { active = false; forget((e as Error).message); return }
        // Back off while rate limited or offline instead of hammering the server.
        failures += 1
        wait = e instanceof ApiError && e.retryAfter ? Math.min(30, e.retryAfter) * 1000
          : Math.min(15000, POLL_MS * 2 ** failures)
        if (active) setError((e as Error).message)
      } finally {
        if (active) timer = window.setTimeout(refresh, wait)
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timer); clearTimeout(animation.current) }
  }, [accept, receive, forget, path, session.token])
  const online = game?.mode === 'online'
  // Keep the emote and chat allowances (and their countdowns) current.
  useEffect(() => {
    if (!online) return
    const id = window.setInterval(() => setNow(performance.now()), 1000)
    return () => clearInterval(id)
  }, [online])
  const allowance = (kind: 'chat' | 'emote') => {
    const local = remaining(sent[kind], kind, now)
    return now < cooldown[kind] ? { left: 0, wait: Math.ceil((cooldown[kind] - now) / 1000) } : local
  }
  async function post(kind: 'chat' | 'emote', body: object) {
    // Count the send at once so the allowance shown never lags behind quick taps; undo it if refused.
    const at = performance.now()
    setSent(s => ({ ...s, [kind]: [...s[kind], at].slice(-ALLOWANCE[kind].burst * 2) }))
    setNow(at)
    try {
      const posted = await request<ChatEvent>(path + '/' + kind, session.token, body)
      setEvents(list => list.some(e => e.id === posted.id) ? list : [...list, posted].slice(-200))
      return posted
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) setCooldown(c => ({ ...c, [kind]: performance.now() + (e.retryAfter || 5) * 1000 }))
      else setSent(s => ({ ...s, [kind]: s[kind].filter(t => t !== at) }))
      throw e
    }
  }
  const sendChat = async (text: string) => { await post('chat', { text }) }
  const sendEmote = async (emote: string, target: PawnColor | null = null) => {
    const posted = await post('emote', { emote, target })
    if (prefs.emotes) setShows(list => [...list, { key: posted.id, emote, from: posted.seat, to: target }])
  }
  const finishShow = useCallback((key: number) => setShows(list => list.filter(s => s.key !== key)), [])
  const toggleMute = (seat: PawnColor) => setMuted(old => {
    const next = new Set(old)
    if (!next.delete(seat)) next.add(seat)
    return next
  })

  async function act(action: 'roll' | 'move', pawn?: number) {
    if (!game || busy || travel || rolling) return
    if (action === 'roll') {
      setRoller(game.current)
    }
    setBusy(true)
    setError('')
    try {
      accept(await request<Match>(path + '/actions', session.token, { action, pawn, revision: game.revision }))
    } catch (e) {
      if (action === 'roll' && clickedAt.current !== null) {
        clickedAt.current = null
        setRoller(null)
      }
      setError((e as Error).message)
    }
    finally { setBusy(false) }
  }

  const ownTurn = game?.mode === 'local' || game?.seat === game?.current
  const active = travel?.before.pawns.find(p => p.id === travel.move.pawn)?.color ?? roller ?? game?.current
  return <div className="play-page" data-chat={online ? (chatOpen ? 'open' : 'closed') : undefined}><main className="match">
    <header><h1><Wordmark/></h1>{(!game || !game.ready || game.phase === 'won') && <button className="quiet" onClick={leave}>Back to lobby</button>}<div className="match-menu">
      <button type="button" className="quiet" aria-label="Game settings" popoverTarget="game-settings">•••</button>
      <div id="game-settings" popover="auto"><SoundToggle/>
        {online && <>
          <label className="preference">Chat messages
            <input type="checkbox" checked={prefs.chat} onChange={e => setPrefs({ ...prefs, chat: e.target.checked })} /></label>
          <label className="preference">Emotes
            <input type="checkbox" checked={prefs.emotes} onChange={e => setPrefs({ ...prefs, emotes: e.target.checked })} /></label>
        </>}
        <button type="button" className="quiet" onClick={async () => {
          const online = game?.mode === 'online' && game.phase !== 'won'
          if (!window.confirm(!online ? "Leave this game? You can resume from the lobby."
            : !game.ready ? "Leave this room? Your seat is given up, and the room closes if nobody else has joined."
            : "Leave this game for good? You can't rejoin. A computer takes your seat if substitutes are on; otherwise you're removed.")) return
          try { await request(path + '/leave', session.token, {}); if (online) forget('You left the game.'); else leave() }
          catch (e) { if (unavailable(e)) forget('Room unavailable.'); else setError((e as Error).message) }
        }}>Leave game</button>
        {game?.can_end && <button type="button" className="quiet" onClick={async () => {
          if (!window.confirm("End this game for everyone? It cannot be resumed.")) return
          try { await request(path + '/end', session.token, {}); forget('Game ended.') }
          catch (e) { setError((e as Error).message) }
        }}>End game</button>}
      </div>
    </div></header>
    {error && <p role="alert">{error}</p>}
    {!game ? <p>Loading game…</p> : <>
      {!game.ready && <p>Room <code>{game.room}</code> · {game.joined}/{game.colors.length} players</p>}
      {!game.ready && <label>Invite link<input readOnly value={location.origin + '/?room=' + game.room}
        onFocus={e => e.target.select()} /></label>}
      <div className="play-space"><div className="arena" data-count={game.colors.length}
        data-warning={timer?.phase === 'move' && game.phase === 'move' && warned === timer.revision || undefined}>
      {game.colors.map(color => {
        const profile = game.profiles[color] || defaultProfile(color)
        const status = game.presence[color]
        return <div key={color} className="seat-card" data-seat={color} data-active={game.ready && active === color} data-presence={status}>
          {(() => {
            const portrait = <span className="portrait">{portraits[profile.avatar]}
              {timer?.phase === 'move' && game.phase === 'move' && color === game.current && <TimerRing key={timer.revision} timer={timer} />}
            </span>
            const reachable = online && game.colors.indexOf(color) < game.joined && !game.out?.includes(color)
            return reachable ? <button type="button" className="portrait-button" aria-haspopup="dialog"
              aria-label={color === game.seat ? 'Send a reaction' : `Send an emote to ${profile.name.trim() || color}`}
              onClick={() => setPicker(picker === color ? null : color)}>{portrait}</button> : portrait
          })()}
          {status && status !== 'online' && <small className="presence">{presenceLabels[status]}</small>}
          <strong>{profile.name.trim() || color}</strong>
          <span className="home-dots" aria-label={game.pawns.filter(p => p.color === color && p.step === 56).length + ' home'}>
            {game.pawns.filter(p => p.color === color).map(p => <i key={p.id} data-home={p.step === 56}/>)}</span>
        </div>
      })}
      <div className="board-frame"><Board pawns={travel ? travel.before.pawns.filter(p => p.id !== travel.move.pawn) : game.pawns} moves={!travel && ownTurn && !busy && !rolling
        ? new Map(game.legal.map(i => [game.current + '-' + (i + 1), () => act('move', i)]))
        : undefined} />
        {travel && <div className="traveling-pawn" ref={traveler} aria-hidden="true"
          style={{color: PAWN_COLOR_HEX[travel.before.pawns.find(p => p.id === travel.move.pawn)!.color]}}>
          <span className="pawn-icon" />
        </div>}</div>
      <div className="dice-dock controls" data-seat={active}>
        <button className="roll" aria-label="Roll die" title="Roll die"
          disabled={!!travel || !game.ready || !ownTurn || busy || rolling || game.phase !== 'roll'} onClick={() => { clickedAt.current = performance.now(); void act('roll') }}>
          <span className={rolling ? 'tumble' : 'rest'}><Die value={travel?.die ?? game.die} rolling={rolling} /></span>
          {timer?.phase === 'roll' && game.phase === 'roll' &&
            <span className="roll-timer" data-hidden={!!travel || rolling || undefined}><TimerRing key={timer.revision} timer={timer} /></span>}
        </button>
      </div></div></div>
      {!travel && game.phase === 'won' && <>
        <Confetti />
        <section className="victory" aria-live="polite">
          <h2>🏆 {game.mode === 'online' && game.seat === game.current ? 'You win!'
            : (game.profiles[game.current]?.name || game.current[0].toUpperCase() + game.current.slice(1)) + ' wins!'}</h2>
          <button className="primary" onClick={leave}>Back to lobby</button>
        </section>
      </>}
      <span className="sr-only" aria-live="polite">{game.message}</span>
    </>}
  </main>
    {game && online && <ChatPanel game={game} events={events} prefs={prefs} setPrefs={setPrefs} muted={muted}
      toggleMute={toggleMute} open={chatOpen} setOpen={setChatOpen} unread={unread} sendChat={sendChat}
      sendEmote={id => sendEmote(id)} chat={allowance('chat')} emote={allowance('emote')} />}
    {game && picker && <EmotePicker key={picker} game={game} seat={picker} muted={muted.has(picker)} toggleMute={() => toggleMute(picker)}
      emote={allowance('emote')} send={sendEmote} close={() => setPicker(null)} />}
    <EmoteLayer shows={shows} done={finishShow} />
  </div>
}

