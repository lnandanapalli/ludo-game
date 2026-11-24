import { useCallback, useEffect, useState } from 'react'
import Board from './Board'
import BoardGrid from './BoardGrid'
import { request, type Match, type Session } from './api'
import Die from './Die'
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

function Play({ session, leave }: { session: Session; leave: () => void }) {
  const [game, setGame] = useState<Match | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const path = '/rooms/' + session.room
  const accept = useCallback((next: Match) => {
    setGame(old => !old || next.revision >= old.revision ? next : old)
  }, [])
  useEffect(() => {
    let active = true
    let timer: number
    async function refresh() {
      try {
        const next = await request<Match>(path, session.token)
        if (active) accept(next)
      } catch (e) {
        if (active) setError((e as Error).message)
      } finally {
        if (active) timer = window.setTimeout(refresh, 1800)
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [accept, path, session.token])

  async function act(action: 'roll' | 'move', pawn?: number) {
    if (!game || busy) return
    setBusy(true)
    setError('')
    try {
      accept(await request<Match>(path + '/actions', session.token, { action, pawn, revision: game.revision }))
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  const ownTurn = game?.mode === 'local' || game?.seat === game?.current
  const prompt = !game?.ready ? 'Waiting for players' : game.phase === 'won' ? game.message
    : !ownTurn ? `Waiting for ${game.current}` : game.phase === 'move' ? 'Tap a highlighted pawn' : 'Tap the die to roll'
  return <main className="match">
    <header><Wordmark/><button className="quiet" onClick={leave}>Back to lobby</button></header>
    {error && <p role="alert">{error}</p>}
    {!game ? <p>Loading game…</p> : <>
      <ul className="players" aria-label="Players and pawns home">{game.colors.map(color =>
        <li key={color} data-seat={color} className={game.current === color ? 'active-seat' : ''}>
          <strong>{color}</strong><small>{game.pawns.filter(p => p.color === color && p.step === 56).length}/4 home</small>
        </li>)}</ul>
      {game.mode === 'online' && <p>Your seat is <b>{game.seat}</b>. {game.joined}/{game.colors.length} joined.
        {' '}Room <code>{game.room}</code></p>}
      {!game.ready && <label>Invite link<input readOnly value={location.origin + location.pathname + '?room=' + game.room}
        onFocus={e => e.target.select()} /></label>}
      <div className="board-frame"><BoardGrid pawns={game.pawns} moves={ownTurn && !busy
        ? new Map(game.legal.map(i => [game.current + '-' + (i + 1), () => act('move', i)]))
        : undefined} /></div>
      <section className="turn-tray controls" data-seat={game.current} aria-label="Turn controls">
        <div><small>{game.phase === 'won' ? 'Game over' : game.current + '’s turn'}</small>
          <h2>{prompt}</h2><p aria-live="polite">{game.message}</p></div>
        <button className="roll" aria-label="Roll die" title={game.die ? 'Last roll: ' + game.die : 'Roll die'}
          disabled={!game.ready || !ownTurn || busy || game.phase !== 'roll'} onClick={() => act('roll')}>
          <Die value={game.die} />
        </button>
      </section>
    </>}
  </main>
}

export default function App() {
  const [session, setSession] = useState(savedSeat)
  const [preferences, setPreferences] = useState<Record<string, boolean>>({})
  const [guestAuto, setGuestAuto] = useState(true)
  const [mode, setMode] = useState<'local' | 'online'>('local')
  const [players, setPlayers] = useState(2)
  const [room, setRoom] = useState(invite)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)
  const [lobby, setLobby] = useState(false)
  async function enter(mode: 'local' | 'online' | 'join') {
    setBusy(true)
    setError('')
    try {
      const seat = mode === 'join'
        ? await request<Session>('/rooms/' + encodeURIComponent(room.trim().toLowerCase()) + '/join', undefined, { auto_move: guestAuto })
        : await request<Session>('/rooms', undefined, { mode, players, auto_move: Object.fromEntries(colors.map(c => [c, preferences[c] ?? true])) })
      localStorage.setItem(storageKey, JSON.stringify(seat))
      history.replaceState(null, '', location.pathname)
      setSession(seat)
      setLobby(false)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (session && !lobby) return <Play key={session.room} session={session} leave={() => setLobby(true)} />
  if (demo) return <main><button onClick={() => setDemo(false)}>Back to lobby</button><Board /></main>
  const colors = players === 2 ? ['red', 'yellow'] : ['red', 'green', 'yellow', 'blue'].slice(0, players)
  return <main className="lobby"><header><Wordmark/><button className="quiet" onClick={() => setDemo(true)}>Pawn demos</button></header>
    {session && <button onClick={() => setLobby(false)}>Resume game</button>}
    <div className="setup-layout"><section className="panel"><h2>Start a game</h2>
      <div className="segmented" aria-label="Game mode">
        <button aria-pressed={mode === 'local'} onClick={() => setMode('local')}>One device</button>
        <button aria-pressed={mode === 'online'} onClick={() => setMode('online')}>Online</button>
      </div>
      <fieldset><legend>Players</legend><div className="numbers">{[2,3,4].map(n =>
        <button key={n} aria-pressed={n === players} onClick={() => setPlayers(n)}>{n}</button>)}</div></fieldset>
      <fieldset><legend>Auto-move the only legal pawn</legend>
        {(mode === 'local' ? colors : ['red']).map(c => <label key={c} data-seat={c} className="preference">
          <span>{c}</span><input type="checkbox" checked={preferences[c] ?? true}
            onChange={e => setPreferences({...preferences, [c]: e.target.checked})}/></label>)}</fieldset>
      <button className="primary" disabled={busy} onClick={() => enter(mode)}>{mode === 'local' ? 'Pass and play' : 'Create online room'}</button>
    </section>
    <form className="panel join" onSubmit={e => { e.preventDefault(); void enter('join') }}><h2>Join a room</h2>
      <label>Room code<input value={room} placeholder="Enter code" onChange={e => setRoom(e.target.value)} required /></label>
      <label className="preference">Auto-move my only legal pawn<input type="checkbox" checked={guestAuto} onChange={e => setGuestAuto(e.target.checked)}/></label>
      <button disabled={busy || !room.trim()}>Join room</button>
    </form></div>
    {error && <p role="alert">{error}</p>}
  </main>
}
