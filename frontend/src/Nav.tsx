import type { MouseEvent, ReactNode } from 'react'
import type { Account } from './api'
import { navigate, type Route } from './routes'

export function Wordmark() {
  return <span className="wordmark"><span className="brand-mark" aria-hidden="true"><i/><i/><i/><i/></span>Ludo</span>
}

export function Link({ to, children, className, current }: { to: Route; children: ReactNode; className?: string; current?: boolean }) {
  return <a href={to} className={className} aria-current={current ? 'page' : undefined} onClick={(e: MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    e.preventDefault()
    navigate(to)
  }}>{children}</a>
}

export default function Nav({ route, account }: { route: Route; account: Account | null }) {
  return <header className="site-header">
    <Link to="/" className="home-link"><h1><Wordmark/></h1></Link>
    <nav aria-label="Main">
      <Link to="/" current={route === '/'}>Play</Link>
      <Link to="/rules" current={route === '/rules'}>How to play</Link>
      <Link to="/about" current={route === '/about'}>About</Link>
      <Link to="/account" current={route === '/account'} className="account-link">
        {account ? <><span aria-hidden="true">👤 </span>{account.username}</> : 'Sign in'}
      </Link>
    </nav>
  </header>
}
