import { useCallback, useEffect, useState } from 'react'
import Board from './Board'
import BoardGrid from './BoardGrid'
import { request, type Match, type Session } from './api'
import './App.css'

const storageKey = 'ludo-seat'
const invite = new URLSearchParams(location.search).get('room') || ''
const dice = ['–', '⚀', '⚁', '⚂', '⚃', '⚄', '⚅']

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
  return <main>
    <header><h1>Ludo</h1><button onClick={leave}>Back to lobby</button></header>
    {error && <p role="alert">{error}</p>}
    {!game ? <p>Loading game…</p> : <>
      <h2>{!game.ready ? 'Waiting for players' : game.phase === 'won' ? game.message : game.current + '’s turn'}</h2>
      {game.mode === 'online' && <p>Your seat is <b>{game.seat}</b>. {game.joined}/{game.colors.length} joined.
        {' '}Room <code>{game.room}</code></p>}
      {!game.ready && <label>Invite link<input readOnly value={location.origin + location.pathname + '?room=' + game.room}
        onFocus={e => e.target.select()} /></label>}
      <BoardGrid pawns={game.pawns} />
      <section className="controls" aria-label="Turn controls">
        <span className="die" aria-label={'Die: ' + game.die}>{dice[game.die]}</span>
        {game.ready && game.phase === 'roll' && <button disabled={!ownTurn || busy} onClick={() => act('roll')}>Roll die</button>}
        {game.ready && game.phase === 'move' && ownTurn && game.legal.map(i => {
          const pawn = game.pawns.find(p => p.id === game.current + '-' + (i+1))!
          const where = pawn.step < 0 ? 'yard' : 'row ' + (pawn.row+1) + ', col ' + (pawn.col+1)
          return <button key={i} disabled={busy} onClick={() => act('move', i)}>Pawn {i+1} ({where})</button>
        })}
        {game.ready && !ownTurn && game.phase !== 'won' && <span>Waiting for {game.current}</span>}
      </section>
      <p aria-live="polite">{game.message}</p>
      <p>{game.colors.map(color => color + ' ' + game.pawns.filter(p => p.color === color && p.step === 56).length + '/4').join(' · ')} home</p>
    </>}
  </main>
}

export default function App() {
  const [session, setSession] = useState(savedSeat)
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
        ? await request<Session>('/rooms/' + encodeURIComponent(room.trim().toLowerCase()) + '/join', undefined, {})
        : await request<Session>('/rooms', undefined, { mode, players })
      localStorage.setItem(storageKey, JSON.stringify(seat))
      history.replaceState(null, '', location.pathname)
      setSession(seat)
      setLobby(false)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (session && !lobby) return <Play key={session.room} session={session} leave={() => setLobby(true)} />
  if (demo) return <main><button onClick={() => setDemo(false)}>Back to lobby</button><Board /></main>
  return <main className="lobby"><h1>Ludo</h1>
    {session && <button onClick={() => setLobby(false)}>Resume game</button>}
    <section><h2>Start a game</h2>
      <label>Players <select value={players} onChange={e => setPlayers(Number(e.target.value))}>
        {[2,3,4].map(n => <option key={n}>{n}</option>)}</select></label>
      <div className="controls"><button disabled={busy} onClick={() => enter('local')}>Pass and play</button>
        <button disabled={busy} onClick={() => enter('online')}>Create online room</button></div>
    </section>
    <form onSubmit={e => { e.preventDefault(); void enter('join') }}><h2>Join a room</h2>
      <label>Room code<input value={room} onChange={e => setRoom(e.target.value)} required /></label>
      <button disabled={busy || !room.trim()}>Join room</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <button onClick={() => setDemo(true)}>Pawn demos</button>
  </main>
}
