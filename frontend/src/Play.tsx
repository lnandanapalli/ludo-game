import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { PAWN_COLOR_HEX } from './types'
import Board from './Board'
import { ApiError, request, unavailable, type Match, type Session } from './api'
import Confetti from './Confetti'
import Die from './Die'
import { Wordmark } from './Nav'
import SoundToggle from './SoundToggle'
import { playChanges } from './sound'
import { defaultProfile, portraits } from './profiles'

const POLL_MS = 1800
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
        const next = await request<Match>(path, session.token)
        failures = 0
        if (active) { accept(next); setError('') }
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
    <header><h1><Wordmark/></h1>{(!game || !game.ready || game.phase === 'won') && <button className="quiet" onClick={leave}>Back to lobby</button>}<div className="match-menu">
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
      {!game.ready && <label>Invite link<input readOnly value={location.origin + '/?room=' + game.room}
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
}

