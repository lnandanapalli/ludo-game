import { useCallback, useEffect, useRef, useState } from 'react'
import Board from './Board'
import BoardGrid from './BoardGrid'
import { request, type Match, type Profile, type Session } from './api'
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

function Play({ session, leave }: { session: Session; leave: () => void }) {
  const [game, setGame] = useState<Match | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const latest = useRef<Match | null>(null)
  const [rolling, setRolling] = useState(false)
  const animation = useRef<number | undefined>(undefined)
  const path = '/rooms/' + session.room
  const accept = useCallback((next: Match) => {
    const old = latest.current
    if (old && next.revision <= old.revision) return
    if (old) playChanges(old, next)
    if (old && next.roll_number > old.roll_number) {
      setRolling(true)
      window.clearTimeout(animation.current)
      animation.current = window.setTimeout(() => setRolling(false), 950)
    }
    latest.current = next
    setGame(next)
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
    return () => { active = false; clearTimeout(timer); clearTimeout(animation.current) }
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
  const active = rolling && game?.roller ? game.roller : game?.current
  return <main className="match">
    <header><Wordmark/><div className="match-menu">
      <button type="button" className="quiet" aria-label="Game settings" popoverTarget="game-settings">•••</button>
      <div id="game-settings" popover="auto"><SoundToggle/>
        <button type="button" className="quiet" onClick={leave}>Back to lobby</button>
      </div>
    </div></header>
    {error && <p role="alert">{error}</p>}
    {!game ? <p>Loading game…</p> : <>
      {!game.ready && <p>Room <code>{game.room}</code> · {game.joined}/{game.colors.length} players</p>}
      {!game.ready && <label>Invite link<input readOnly value={location.origin + location.pathname + '?room=' + game.room}
        onFocus={e => e.target.select()} /></label>}
      <div className="play-space"><div className="arena" data-count={game.colors.length}>
      {game.colors.map(color => {
        const profile = game.profiles[color] || defaultProfile(color)
        return <div key={color} className="seat-card" data-seat={color} data-active={game.ready && active === color}>
          <span className="portrait">{portraits[profile.avatar]}</span>
          <strong>{profile.name.trim() || color}</strong>
          <span className="home-dots" aria-label={game.pawns.filter(p => p.color === color && p.step === 56).length + ' home'}>
            {game.pawns.filter(p => p.color === color).map(p => <i key={p.id} data-home={p.step === 56}/>)}</span>
        </div>
      })}
      <div className="board-frame"><BoardGrid pawns={game.pawns} moves={ownTurn && !busy && !rolling
        ? new Map(game.legal.map(i => [game.current + '-' + (i + 1), () => act('move', i)]))
        : undefined} /></div>
      <div className="dice-dock controls" data-seat={active}>
        <button className="roll" aria-label="Roll die" title="Roll die"
          disabled={!game.ready || !ownTurn || busy || rolling || game.phase !== 'roll'} onClick={() => act('roll')}>
          <span key={game.roll_number} className={rolling ? 'tumble' : 'rest'}><Die value={game.die} /></span>
        </button>
      </div></div></div>
      {game.phase === 'won' && <h2 className="victory">🏆 {game.profiles[game.current]?.name || game.current} wins!</h2>}
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
        ? await request<Session>('/rooms/' + encodeURIComponent(room.trim().toLowerCase()) + '/join', undefined, { profile: guestProfile, auto_move: guestAuto })
        : await request<Session>('/rooms', undefined, { mode, players, profiles, auto_move: Object.fromEntries(colors.map(c => [c, preferences[c] ?? true])) })
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
      {(mode === 'local' ? colors : ['red']).map(c => <ProfilePicker key={c} seat={c}
        profile={profiles[c] || defaultProfile(c)} change={profile => setProfiles({...profiles, [c]: profile})}/>)}
      <fieldset><legend>Auto-move the only legal pawn</legend>
        {(mode === 'local' ? colors : ['red']).map(c => <label key={c} data-seat={c} className="preference">
          <span>{c}</span><input type="checkbox" checked={preferences[c] ?? true}
            onChange={e => setPreferences({...preferences, [c]: e.target.checked})}/></label>)}</fieldset>
      <SoundToggle/>
      <button className="primary" disabled={busy} onClick={() => enter(mode)}>{mode === 'local' ? 'Pass and play' : 'Create online room'}</button>
    </section>
    <form className="panel join" onSubmit={e => { e.preventDefault(); void enter('join') }}><h2>Join a room</h2>
      <label>Room code<input value={room} placeholder="Enter code" onChange={e => setRoom(e.target.value)} required /></label>
      <ProfilePicker seat="guest" profile={guestProfile} change={setGuestProfile}/>
      <label className="preference">Auto-move my only legal pawn<input type="checkbox" checked={guestAuto} onChange={e => setGuestAuto(e.target.checked)}/></label>
      <button disabled={busy || !room.trim()}>Join room</button>
    </form></div>
    {error && <p role="alert">{error}</p>}
  </main>
}
