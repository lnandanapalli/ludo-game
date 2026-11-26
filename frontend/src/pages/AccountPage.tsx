import { useState, type FormEvent } from 'react'
import { request, setAccountToken, type Account, type Profile } from '../api'
import { portraits } from '../profiles'

function Field({ label, ...input }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <label className="field">{label}<input {...input} required /></label>
}

function SignForms({ onAccount }: { onAccount: (account: Account) => void }) {
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (mode === 'up' && password !== confirm) { setError('The passwords do not match.'); return }
    setBusy(true)
    setError('')
    try {
      const result = await request<{ token: string; account: Account }>(mode === 'in' ? '/sessions' : '/accounts',
        undefined, { username: username.trim(), password })
      setAccountToken(result.token)
      onAccount(result.account)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return <section className="panel account-forms">
    <div className="segmented" aria-label="Account">
      <button type="button" aria-pressed={mode === 'in'} onClick={() => setMode('in')}>Sign in</button>
      <button type="button" aria-pressed={mode === 'up'} onClick={() => setMode('up')}>Create account</button>
    </div>
    <p className="hint">An account is optional. It keeps your name and avatar, records your wins, and lets you resume online games on any device.</p>
    <form onSubmit={submit}>
      <Field label="Username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username"
        minLength={3} maxLength={20} pattern="[A-Za-z0-9_]{3,20}" title="3–20 letters, digits or underscores" />
      <Field label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)}
        autoComplete={mode === 'in' ? 'current-password' : 'new-password'} minLength={mode === 'up' ? 8 : 1} maxLength={128} />
      {mode === 'up' && <Field label="Confirm password" type="password" value={confirm}
        onChange={e => setConfirm(e.target.value)} autoComplete="new-password" minLength={8} maxLength={128} />}
      {error && <p role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{mode === 'in' ? 'Sign in' : 'Create account'}</button>
    </form>
  </section>
}

function ProfileForm({ account, onAccount }: { account: Account; onAccount: (account: Account) => void }) {
  const [profile, setProfile] = useState<Profile>(account.profile)
  const [status, setStatus] = useState('')
  async function save(e: FormEvent) {
    e.preventDefault()
    try {
      onAccount(await request<Account>('/me/profile', undefined, profile, 'PUT'))
      setStatus('Saved.')
    } catch (err) { setStatus((err as Error).message) }
  }
  return <form className="panel" onSubmit={save}>
    <h3>Profile</h3>
    <label className="field">Display name
      <input value={profile.name} maxLength={24} placeholder={account.username}
        onChange={e => { setProfile({ ...profile, name: e.target.value }); setStatus('') }} />
    </label>
    <div className="portraits" role="group" aria-label="Avatar">{Object.entries(portraits).map(([id, face]) =>
      <button key={id} type="button" aria-label={id} aria-pressed={profile.avatar === id}
        onClick={() => { setProfile({ ...profile, avatar: id }); setStatus('') }}>{face}</button>)}</div>
    <button className="primary">Save profile</button>
    {status && <p role="status">{status}</p>}
  </form>
}

function Security({ onSignOut }: { onSignOut: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [status, setStatus] = useState('')
  async function change(e: FormEvent) {
    e.preventDefault()
    try {
      await request('/me/password', undefined, { current, new: next })
      setCurrent(''); setNext('')
      setStatus('Password changed. Other devices were signed out.')
    } catch (err) { setStatus((err as Error).message) }
  }
  async function remove() {
    const password = window.prompt('Delete your account and its history for good? Enter your password to confirm.')
    if (!password) return
    try {
      await request('/me/delete', undefined, { password })
      setAccountToken(null)
      onSignOut()
    } catch (err) { setStatus((err as Error).message) }
  }
  return <section className="panel">
    <h3>Security</h3>
    <form onSubmit={change}>
      <Field label="Current password" type="password" value={current} onChange={e => setCurrent(e.target.value)} autoComplete="current-password" maxLength={128} />
      <Field label="New password" type="password" value={next} onChange={e => setNext(e.target.value)} autoComplete="new-password" minLength={8} maxLength={128} />
      <button>Change password</button>
    </form>
    {status && <p role="status">{status}</p>}
    <button type="button" className="danger" onClick={remove}>Delete account</button>
  </section>
}

export default function AccountPage({ account, onAccount, onSignOut }: {
  account: Account | null; onAccount: (account: Account) => void; onSignOut: () => void
}) {
  if (!account) return <div className="page"><h2>Your account</h2><SignForms onAccount={onAccount} /></div>
  const { games, wins } = account.stats
  return <div className="page account-page">
    <div className="page-title"><h2>Hi, {account.profile.name || account.username}</h2>
      <button type="button" onClick={async () => {
        await request('/sessions', undefined, undefined, 'DELETE').catch(() => undefined)
        setAccountToken(null)
        onSignOut()
      }}>Sign out</button></div>
    <section className="panel stats" aria-label="Your record">
      <div><strong>{games}</strong><small>games finished</small></div>
      <div><strong>{wins}</strong><small>wins</small></div>
      <div><strong>{games ? Math.round(wins / games * 100) + '%' : '–'}</strong><small>win rate</small></div>
    </section>
    <ProfileForm account={account} onAccount={onAccount} />
    <Security onSignOut={onSignOut} />
  </div>
}
