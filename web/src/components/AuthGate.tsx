import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<{ authenticated: boolean; required: boolean } | null>(null)
  const [key, setKey] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.session().then(setSession).catch(() => setError('Cannot reach the API. Check the server and reload.')) }, [])
  useEffect(() => {
    const expired = () => { setSession({ authenticated: false, required: true }); setError('Please sign in again.') }
    window.addEventListener('scribebench-session-expired', expired)
    return () => window.removeEventListener('scribebench-session-expired', expired)
  }, [])
  if (session?.authenticated) return <>{session.required && <button className="sign-out" onClick={async () => { await api.logout(); window.location.reload() }}>Sign out</button>}{children}</>
  return <main className="login-page"><form className="login-card" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await api.login(key); setKey(''); setSession(await api.session()) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Sign in failed') }
    finally { setBusy(false) }
  }}>
    <span className="scope-label">ScribeBench · private workspace</span>
    <h1>{session ? 'Sign in to review' : 'Connecting to your workspace…'}</h1>
    <p>Your workspace key stays out of browser storage. Sessions expire after eight hours.</p>
    {session && <><label>Workspace key<input type="password" autoComplete="current-password" required value={key} onChange={e => setKey(e.target.value)} /></label><button className="primary" disabled={busy}>Sign in</button></>}
    {error && <p role="alert">{error}</p>}
  </form></main>
}
