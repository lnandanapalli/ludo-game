import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { PAWN_COLOR_HEX } from './types'
import BoardGrid from './BoardGrid'
import { ApiError, request, type Match, type Profile, type Session } from './api'
import Die from './Die'
import SoundToggle from './SoundToggle'
import { playChanges } from './sound'
import ProfilePicker from './ProfilePicker'
import { defaultProfile, portraits } from './profiles'
import './App.css'

const storageKey = 'ludo-seat'
const invite = new URLSearchParams(location.search).get('room') || ''
function Wordmark() {
  return <h1 className="wordmark"><span className="brand-mark" aria-hidden="true"><i/><i/><i/><i/></span>Ludo</h1>
}

function savedSeat(): Session | null {
  try {
    const seat = JSON.parse(localStorage.getItem(storageKey) || 'null')
    return seat?.token && seat.room && (!invite || invite === seat.room) ? seat : null
  } catch { return null }
}

function unavailable(e: unknown) {
  return e instanceof ApiError && [401, 403, 404, 410].includes(e.status)
}

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

function Play({ session, leave, forget }: { session: Session; leave: () => void; forget: (message: string) => void }) {
  const [game, setGame] = useState<Match | null>(null)
  const [travel, setTravel] = useState<{ move: NonNullable<Match['last_move']>; before: Match; die: number; delay: number } | null>(null)
  const traveler = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    if (!travel || !traveler.current) return
    const path = travel.move.path
    const frames: Keyframe[] = []
    path.forEach(([row, col], i) => {
      if (i) {
        const [r, c] = path[i - 1]
        frames.push({ transform: `translate(${(c + col) * 50}%, ${(r + row) * 50 - 18}%)`, offset: (i - .5) / (path.length - 1) })
      }
      frames.push({ transform: `translate(${col * 100}%, ${row * 100}%)`, offset: i / (path.length - 1) })
    })
    const movement = traveler.current.animate(frames, {
      duration: travelDuration(path), delay: travel.delay, fill: 'both',
    })
    movement.onfinish = () => setTravel(null)
    return () => movement.cancel()
  }, [travel])
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
    async function refresh() {
      try {
        const next = await request<Match>(path, session.token)
        if (active) { accept(next); setError('') }
      } catch (e) {
        if (active && unavailable(e)) { active = false; forget((e as Error).message); return }
        if (active) setError((e as Error).message)
      } finally {
        if (active) timer = window.setTimeout(refresh, 1800)
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timer); clearTimeout(animation.current) }
  }, [accept, forget, path, session.token])

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
  return <main className="match">
    <header><Wordmark/>{(!game || !game.ready || game.phase === 'won') && <button className="quiet" onClick={leave}>Back to lobby</button>}<div className="match-menu">
      <button type="button" className="quiet" aria-label="Game settings" popoverTarget="game-settings">•••</button>
      <div id="game-settings" popover="auto"><SoundToggle/>
        <button type="button" className="quiet" onClick={async () => {
          const online = game?.mode === 'online' && game.phase !== 'won'
          if (!window.confirm(online
            ? "Leave this game for good? You can't rejoin. A computer takes your seat if substitutes are on; otherwise you're removed."
            : "Leave this game? You can resume from the lobby.")) return
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
      {!game.ready && <label>Invite link<input readOnly value={location.origin + location.pathname + '?room=' + game.room}
        onFocus={e => e.target.select()} /></label>}
      <div className="play-space"><div className="arena" data-count={game.colors.length}
        data-warning={timer?.phase === 'move' && game.phase === 'move' && warned === timer.revision || undefined}>
      {game.colors.map(color => {
        const profile = game.profiles[color] || defaultProfile(color)
        const status = game.presence[color]
        return <div key={color} className="seat-card" data-seat={color} data-active={game.ready && active === color} data-presence={status}>
          <span className="portrait">{portraits[profile.avatar]}
            {timer?.phase === 'move' && game.phase === 'move' && color === game.current && <TimerRing key={timer.revision} timer={timer} />}
          </span>
          {status && status !== 'online' && <small className="presence">{presenceLabels[status]}</small>}
          <strong>{profile.name.trim() || color}</strong>
          <span className="home-dots" aria-label={game.pawns.filter(p => p.color === color && p.step === 56).length + ' home'}>
            {game.pawns.filter(p => p.color === color).map(p => <i key={p.id} data-home={p.step === 56}/>)}</span>
        </div>
      })}
      <div className="board-frame"><BoardGrid pawns={travel ? travel.before.pawns.filter(p => p.id !== travel.move.pawn) : game.pawns} moves={!travel && ownTurn && !busy && !rolling
        ? new Map(game.legal.map(i => [game.current + '-' + (i + 1), () => act('move', i)]))
        : undefined} />
        {travel && <div className="traveling-pawn" ref={traveler} aria-hidden="true"
          style={{color: PAWN_COLOR_HEX[travel.before.pawns.find(p => p.id === travel.move.pawn)!.color]}}>
          <span className="pawn-icon" />
        </div>}</div>
      <div className="dice-dock controls" data-seat={active}>
        <button className="roll" aria-label="Roll die" title="Roll die"
          disabled={!!travel || !game.ready || !ownTurn || busy || rolling || game.phase !== 'roll'} onClick={() => { clickedAt.current = performance.now(); void act('roll') }}>
          <span className={rolling ? 'tumble' : 'rest'}><Die value={travel?.die ?? game.die} /></span>
          {timer?.phase === 'roll' && game.phase === 'roll' &&
            <span className="roll-timer" data-hidden={!!travel || rolling || undefined}><TimerRing key={timer.revision} timer={timer} /></span>}
        </button>
      </div></div></div>
      {!travel && game.phase === 'won' && <h2 className="victory">🏆 {game.profiles[game.current]?.name || game.current} wins!</h2>}
      <span className="sr-only" aria-live="polite">{game.message}</span>
    </>}
  </main>
}

export default function App() {
  const [session, setSession] = useState(savedSeat)
  const [profiles, setProfiles] = useState<Record<string, Profile>>({})
  const [guestProfile, setGuestProfile] = useState(defaultProfile("guest"))
  const [preferences, setPreferences] = useState<Record<string, boolean>>({})
  const [guestAuto, setGuestAuto] = useState(true)
  const [substitutes, setSubstitutes] = useState(true)
  const [mode, setMode] = useState<Match['mode']>(invite ? 'online' : session?.mode || 'local')
  const [preview, setPreview] = useState<Match | null>(null)
  const [players, setPlayers] = useState(2)
  const [room, setRoom] = useState(invite)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [lobby, setLobby] = useState(true)
  const forget = useCallback((message: string) => {
    localStorage.removeItem(storageKey)
    setPreview(null)
    setSession(null)
    setLobby(true)
    setError(message)
  }, [])
  useEffect(() => {
    if (!session || !lobby) return
    let active = true
    request<Match>('/rooms/' + session.room + '?preview=true', session.token).then(match => {
      if (!active) return
      if (match.phase === 'won') forget('Your previous game finished.')
      else setPreview(match)
    }).catch(e => { if (!active) return; if (unavailable(e)) forget(e.message); else setError('Could not check your saved game. Refresh to retry.') })
    return () => { active = false }
  }, [session, lobby, forget])
  async function enter(mode: 'local' | 'online' | 'join') {
    const code = room.trim().toLowerCase()
    if (mode === 'join' && session?.room === code) {
      setError('You already have a seat in this room. Use Resume game.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const seat = mode === 'join'
        ? await request<Session>('/rooms/' + encodeURIComponent(code) + '/join', undefined, { profile: guestProfile, auto_move: guestAuto })
        : await request<Session>('/rooms', undefined, { mode, players, profiles, substitutes: mode === 'online' && substitutes, auto_move: Object.fromEntries(colors.map(c => [c, preferences[c] ?? true])) })
      seat.mode = mode === 'join' ? 'online' : mode
      setMode(seat.mode)
      setPreview(null)
      localStorage.setItem(storageKey, JSON.stringify(seat))
      history.replaceState(null, '', location.pathname)
      setSession(seat)
      setLobby(false)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (session && !lobby) return <Play key={session.room} session={session} leave={() => setLobby(true)} forget={forget} />
  const colors = players === 2 ? ['red', 'yellow'] : ['red', 'green', 'yellow', 'blue'].slice(0, players)
  return <main className="lobby"><header><Wordmark/></header>
    <div className="setup-layout"><section className="panel"><h2>Start a game</h2>
      <div className="segmented" aria-label="Game mode">
        <button aria-pressed={mode === 'local'} onClick={() => setMode('local')}>One device</button>
        <button aria-pressed={mode === 'online'} onClick={() => setMode('online')}>Online</button>
      </div>
      {session && preview?.mode === mode && <section className="saved-match" aria-label="Saved game">
        <div><strong>{mode === 'local' ? 'Saved game on this device' : 'Room ' + preview.room}</strong>
          <p>{preview.colors.slice(0, preview.mode === 'local' ? preview.colors.length : preview.joined)
            .map(c => preview.profiles[c]?.name || c[0].toUpperCase() + c.slice(1)).join(' · ')}</p>
          <small>{preview.ready ? <>
            {preview.started_at ? 'Started ' + new Date(preview.started_at * 1000).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}) : 'Start time unavailable'}
            {' · '}{preview.profiles[preview.current]?.name || preview.current}’s turn
          </> : 'Waiting for players · ' + preview.joined + '/' + preview.colors.length}</small>
        </div>
        <div className="saved-actions"><button onClick={() => setLobby(false)}>Resume game</button>
          <button aria-label="Dismiss saved game" title="Dismiss saved game" onClick={() => {
            if (window.confirm('Remove this saved game from this browser?')) forget('')
          }}>×</button></div>
      </section>}
      <fieldset><legend>Players</legend><div className="numbers">{[2,3,4].map(n =>
        <button key={n} aria-pressed={n === players} onClick={() => setPlayers(n)}>{n}</button>)}</div></fieldset>
      {(mode === 'local' ? colors : ['red']).map(c => <ProfilePicker key={c} seat={c}
        autoMove={preferences[c] ?? true} onAutoMove={enabled => setPreferences({...preferences, [c]: enabled})}
        profile={profiles[c] || defaultProfile(c)} change={profile => setProfiles({...profiles, [c]: profile})}/>)}
      {mode === 'online' && <label className="preference">Computer substitutes after 5 minutes offline
        <input type="checkbox" checked={substitutes} onChange={e => setSubstitutes(e.target.checked)} /></label>}
      <SoundToggle/>
      <button className="primary" disabled={busy} onClick={() => enter(mode)}>{mode === 'local' ? 'Pass and play' : 'Create online room'}</button>
    </section>
    <form className="panel join" onSubmit={e => { e.preventDefault(); void enter('join') }}><h2>Join a room</h2>
      <label>Room code<input value={room} placeholder="Enter code" onChange={e => setRoom(e.target.value)} required /></label>
      <ProfilePicker seat="guest" profile={guestProfile} change={setGuestProfile} autoMove={guestAuto} onAutoMove={setGuestAuto}/>
      <button disabled={busy || !room.trim()}>Join room</button>
    </form></div>
    {error && <p role="alert">{error}</p>}
  </main>
}
