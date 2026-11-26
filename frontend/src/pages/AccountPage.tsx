import { useEffect, useState, type FormEvent } from 'react'
import { request, setAccountToken, type Account, type Profile } from '../api'
import { portraits } from '../profiles'

function Field({ label, ...input }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <label className="field">{label}<input {...input} required /></label>
}

type Step = 'in' | 'up' | 'verify' | 'forgot' | 'reset'
const RESEND_SECONDS = 60

function useCountdown() {
  const [until, setUntil] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (until <= now) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [until, now])
  return [Math.max(0, Math.round((until - now) / 1000)), () => { setNow(Date.now()); setUntil(Date.now() + RESEND_SECONDS * 1000) }] as const
}

function SignForms({ onAccount }: { onAccount: (account: Account) => void }) {
  const [step, setStep] = useState<Step>('in')
  const [login, setLogin] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [wait, startWait] = useCountdown()
  const go = (next: Step, message = '') => { setStep(next); setError(''); setNote(message); setCode('') }
  const signedIn = (result: { token: string; account: Account }) => { setAccountToken(result.token); onAccount(result.account) }
  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError('')
    try { await action() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  function submit(e: FormEvent) {
    e.preventDefault()
    if ((step === 'up' || step === 'reset') && password !== confirm) { setError('The passwords do not match.'); return }
    void run(async () => {
      if (step === 'in') signedIn(await request('/sessions', undefined, { login: login.trim(), password }))
      else if (step === 'up') {
        await request('/accounts', undefined, { username: username.trim(), email: email.trim(), password })
        startWait()
        go('verify', `We sent a 6-digit code to ${email.trim()}. It expires in 10 minutes.`)
      } else if (step === 'verify') signedIn(await request('/accounts/verify', undefined, { email: email.trim(), code }))
      else if (step === 'forgot') {
        const reply = await request<{ detail: string }>('/password/forgot', undefined, { email: email.trim() })
        startWait()
        go('reset', reply.detail)
      } else signedIn(await request('/password/reset', undefined, { email: email.trim(), code, password }))
    })
  }
  const resend = () => void run(async () => {
    if (step === 'verify') await request('/accounts/resend', undefined, { email: email.trim() })
    else await request('/password/forgot', undefined, { email: email.trim() })
    startWait()
    setCode('')
    setNote('We sent a new code. Only the newest code works.')
  })
  const codeField = <Field label="6-digit code" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
    inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} autoFocus />
  const passwordFields = (label: string) => <>
    <Field label={label} type="password" value={password} onChange={e => setPassword(e.target.value)}
      autoComplete="new-password" minLength={8} maxLength={128} />
    <Field label="Confirm password" type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
      autoComplete="new-password" minLength={8} maxLength={128} />
  </>
  const titles: Record<Step, string> = { in: 'Sign in', up: 'Create account', verify: 'Check your email',
    forgot: 'Reset your password', reset: 'Choose a new password' }
  return <section className="panel account-forms">
    {step === 'in' || step === 'up' ? <div className="segmented" aria-label="Account">
      <button type="button" aria-pressed={step === 'in'} onClick={() => go('in')}>Sign in</button>
      <button type="button" aria-pressed={step === 'up'} onClick={() => go('up')}>Create account</button>
    </div> : <h3>{titles[step]}</h3>}
    {step === 'in' || step === 'up'
      ? <p className="hint">An account is optional. It keeps your name and avatar, records your wins, and lets you resume online games on any device.</p>
      : note && <p role="status">{note}</p>}
    <form onSubmit={submit}>
      {step === 'in' && <>
        <Field label="Username or email" value={login} onChange={e => setLogin(e.target.value)} autoComplete="username" maxLength={254} />
        <Field label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)}
          autoComplete="current-password" maxLength={128} />
      </>}
      {step === 'up' && <>
        <Field label="Username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username"
          minLength={3} maxLength={20} pattern="[A-Za-z0-9_]{3,20}" title="3–20 letters, digits or underscores" />
        <Field label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" maxLength={254} />
        {passwordFields('Password')}
      </>}
      {step === 'verify' && codeField}
      {step === 'forgot' && <Field label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)}
        autoComplete="email" maxLength={254} />}
      {step === 'reset' && <>{codeField}{passwordFields('New password')}</>}
      {error && <p role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{{ in: 'Sign in', up: 'Create account', verify: 'Verify email',
        forgot: 'Send code', reset: 'Set password and sign in' }[step]}</button>
    </form>
    <div className="form-links">
      {step === 'in' && <button type="button" className="link" onClick={() => go('forgot')}>Forgot password?</button>}
      {(step === 'verify' || step === 'reset') && <button type="button" className="link" disabled={busy || wait > 0}
        onClick={resend}>{wait ? `Resend code in ${wait}s` : 'Resend code'}</button>}
      {step === 'verify' && <button type="button" className="link" onClick={() => go('up')}>Use a different email</button>}
      {(step === 'forgot' || step === 'reset') && <button type="button" className="link" onClick={() => go('in')}>Back to sign in</button>}
    </div>
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
    <p className="hint">Signed in as <strong>{account.username}</strong> · {account.email}</p>
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
