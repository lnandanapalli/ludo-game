import { useCallback, useEffect, useState } from 'react'
import { accountToken, request, unavailable, type Account, type Match, type Profile, type Session } from './api'
import Nav from './Nav'
import { currentRoute, navigate, type Route } from './routes'
import Play from './Play'
import ProfilePicker from './ProfilePicker'
import SoundToggle from './SoundToggle'
import { defaultProfile } from './profiles'
import About from './pages/About'
import AccountPage from './pages/AccountPage'
import Rules from './pages/Rules'
import './App.css'

const storageKey = 'ludo-seat'
const invite = new URLSearchParams(location.search).get('room') || ''

function savedSeat(): Session | null {
  try {
    const seat = JSON.parse(localStorage.getItem(storageKey) || 'null')
    return seat?.token && seat.room && (!invite || invite === seat.room) ? seat : null
  } catch { return null }
}

function storeSeat(seat: Session | null) {
  try {
    if (seat) localStorage.setItem(storageKey, JSON.stringify(seat))
    else localStorage.removeItem(storageKey)
  } catch { /* Without storage the seat lasts until the page closes. */ }
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute)
  const [account, setAccount] = useState<Account | null>(null)
  const [session, setSession] = useState(savedSeat)
  const [profiles, setProfiles] = useState<Record<string, Profile>>({})
  const [guestEdit, setGuestEdit] = useState<Profile | null>(null)
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
  useEffect(() => {
    const onRoute = () => setRoute(currentRoute())
    const onAccount = () => { if (!accountToken()) setAccount(null) }
    window.addEventListener('popstate', onRoute)
    window.addEventListener('ludo-account', onAccount)
    return () => { window.removeEventListener('popstate', onRoute); window.removeEventListener('ludo-account', onAccount) }
  }, [])
  // Load the signed-in account, and refresh its games and record whenever the lobby is shown.
  useEffect(() => {
    if (!accountToken() || (session && !lobby)) return
    let active = true
    request<Account>('/me').then(me => { if (active) setAccount(me) }).catch(() => undefined)
    return () => { active = false }
  }, [lobby, route, session])
  const forget = useCallback((message: string) => {
    storeSeat(null)
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
        : await request<Session>('/rooms', undefined, {
          mode, players, substitutes: mode === 'online' && substitutes,
          profiles: Object.fromEntries(colors.map(c => [c, profileFor(c)])),
          auto_move: Object.fromEntries(colors.map(c => [c, preferences[c] ?? true])),
        })
      seat.mode = mode === 'join' ? 'online' : mode
      open(seat)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  function open(seat: Session) {
    setMode(seat.mode || 'online')
    setPreview(null)
    storeSeat(seat)
    history.replaceState(null, '', '/')
    setRoute('/')
    setSession(seat)
    setLobby(false)
  }
  async function reclaim(room: string) {
    setBusy(true)
    setError('')
    try {
      open(await request<Session>('/rooms/' + encodeURIComponent(room) + '/reclaim', undefined, {}))
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (session && !lobby) return <Play key={session.room + session.token} session={session} leave={() => setLobby(true)} forget={forget} />
  const colors = players === 2 ? ['red', 'yellow'] : ['red', 'green', 'yellow', 'blue'].slice(0, players)
  // A signed-in player's saved profile fills their own seat until they edit it here.
  const profileFor = (seat: string) => profiles[seat] || (seat === 'red' && account ? account.profile : defaultProfile(seat))
  const guestProfile = guestEdit ?? account?.profile ?? defaultProfile('guest')
  const otherGames = account?.games.filter(g => g.room !== session?.room) ?? []
  return <main className="lobby"><Nav route={route} account={account} />
    {route === '/rules' ? <Rules /> : route === '/about' ? <About /> : route === '/account'
      ? <AccountPage account={account} onAccount={setAccount} onSignOut={() => { setAccount(null); navigate('/') }} />
      : <><div className="setup-layout"><section className="panel"><h2>Start a game</h2>
      <div className="segmented" aria-label="Game mode">
        <button aria-pressed={mode === 'local'} onClick={() => setMode('local')}>One device</button>
        <button aria-pressed={mode === 'online'} onClick={() => setMode('online')}>Online</button>
      </div>
      {mode === 'online' && otherGames.length > 0 && <section className="saved-match your-games" aria-label="Your online games">
        <strong>Your online games</strong>
        <ul>{otherGames.map(g => <li key={g.room} data-seat={g.color}>
          <span><span className="seat-dot" aria-hidden="true" />{g.players.join(' · ')}</span>
          <button disabled={busy} onClick={() => reclaim(g.room)} aria-label={'Resume room ' + g.room}>Resume</button>
        </li>)}</ul>
      </section>}
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
        profile={profileFor(c)} change={profile => setProfiles({...profiles, [c]: profile})}/>)}
      {mode === 'online' && <label className="preference">Computer substitutes after 5 minutes offline
        <input type="checkbox" checked={substitutes} onChange={e => setSubstitutes(e.target.checked)} /></label>}
      <SoundToggle/>
      <button className="primary" disabled={busy} onClick={() => enter(mode)}>{mode === 'local' ? 'Pass and play' : 'Create online room'}</button>
    </section>
    <form className="panel join" onSubmit={e => { e.preventDefault(); void enter('join') }}><h2>Join a room</h2>
      <label>Room code<input value={room} placeholder="Enter code" onChange={e => setRoom(e.target.value)} required /></label>
      <ProfilePicker seat="guest" profile={guestProfile} change={setGuestEdit} autoMove={guestAuto} onAutoMove={setGuestAuto}/>
      <button disabled={busy || !room.trim()}>Join room</button>
    </form></div>
    {error && <p role="alert">{error}</p>}
    {!account && <p className="hint">Playing as a guest. <a href="/account" onClick={e => { e.preventDefault(); navigate('/account') }}>Sign in</a> to keep your wins and resume online games on any device.</p>}
    </>}
  </main>
}
