import { useEffect, useState } from 'react'
import { api, type Operations, type PilotStatus } from '../api'
import type { Job } from '../types'
import { shortId } from '../lib'

export function PilotView({ jobs }: { jobs: Job[] }) {
  const [pilot, setPilot] = useState<PilotStatus | null>(null)
  const [ops, setOps] = useState<Operations | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [jobId, setJobId] = useState('')
  const [usability, setUsability] = useState('')
  const [accuracy, setAccuracy] = useState('')
  const [issue, setIssue] = useState('none')
  const [comment, setComment] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const refresh = async () => {
    try {
      const status = await api.pilot(); setPilot(status); setError('')
      if (['local', 'operator'].includes(status.actor)) setOps(await api.operations())
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load operational status') }
  }
  useEffect(() => {
    let active = true
    api.pilot().then(async status => {
      const snapshot = ['local', 'operator'].includes(status.actor) ? await api.operations() : null
      if (active) { setPilot(status); setOps(snapshot) }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Unable to load operational status') })
    return () => { active = false }
  }, [])
  return <main className="list-view pilot-view">
    <div className="page-heading"><div><p className="eyebrow">CONTROLLED EVALUATION</p><h1>Pilot & operations</h1><p>Operational evidence first. Real patient information never.</p></div><button className="secondary" onClick={refresh}>Refresh status</button></div>
    {error && <p role="alert" className="inline-warning">{error}</p>}
    <section className="pilot-banner"><div><span className="status-chip">{pilot?.status === 'active' ? 'Authorised pilot' : pilot?.status === 'expired' ? 'Pilot expired' : 'Awaiting authorisation'}</span><h2>{pilot?.status === 'active' ? 'A bounded, synthetic-only pilot' : 'Built for a careful first pilot'}</h2><p>{pilot?.status === 'active' ? `Pilot ${pilot.pilot_id} · closes ${new Date(pilot.expires_at!).toLocaleString()}` : 'No participants have been invited by this build. Add the approved owner, participants and dates before collecting pilot evidence.'}</p></div><div className="pilot-boundary"><strong>Synthetic cases only</strong><span>Local models · explicit approval · recorded feedback</span></div></section>
    <div className="operational-stats">
      <article><span>Authorised participants</span><strong>{pilot?.participant_count ?? '—'}</strong><small>From the operator-approved manifest</small></article>
      <article><span>Pilot submissions</span><strong>{pilot ? pilot.counts.job_submitted ?? 0 : '—'}</strong><small>Recorded under this pilot ID</small></article>
      <article><span>Feedback entries</span><strong>{pilot ? pilot.counts.feedback ?? 0 : '—'}</strong><small>Submitted by signed-in participants</small></article>
    </div>
    <div className="operations-grid">
      <section className="operations-panel"><h2>Service snapshot</h2><p>Point-in-time API state. This is not an uptime or deployment certification.</p>
        <dl>{ops ? <>
          <div><dt>Access boundary</dt><dd>{ops.secure_cookies && ops.authentication_required ? 'Secure-cookie authentication configured' : 'Local development · not a secured deployment'}</dd></div>
          <div><dt>Waiting jobs</dt><dd>{ops.queue_depth}</dd></div>
          <div><dt>Oldest pending job</dt><dd>{ops.oldest_pending_seconds}s</dd></div>
          <div><dt>Failures · last 15 minutes</dt><dd>{ops.failed_last_15_minutes}</dd></div>
        </> : <div><dt>Operator visibility</dt><dd>Sign in as the operator to inspect service metrics.</dd></div>}</dl>
        {pilot && ['local', 'operator'].includes(pilot.actor) && <a className="secondary" href="/api/pilot/report" download>Download pilot evidence</a>}
      </section>
      <section className="operations-panel"><h2>What opens the pilot?</h2><ol className="readiness-list"><li><strong>Authorise the people and window</strong><span>Owner approval, individual credentials, start and expiry dates.</span></li><li><strong>Qualify the deployment</strong><span>HTTPS, restored backup, release rollback and an alert recipient.</span></li><li><strong>Review synthetic cases</strong><span>Library cases only; record errors, edits and participant feedback.</span></li></ol><p>Build preparation does not mark these operational gates complete.</p></section>
    </div>
    <section className="operations-panel feedback-panel"><h2>Participant feedback</h2><p>Rate a reviewed synthetic draft. Do not include names, identifiers or real patient information.</p>
      {!pilot?.can_submit_feedback ? <div className="feedback-locked">Feedback opens only for a signed-in, authorised participant during an active pilot.</div> : <form onSubmit={async e => {
        e.preventDefault(); setBusy(true); setMessage('')
        try { await api.feedback({ job_id: jobId, usability: Number(usability), accuracy: Number(accuracy), issue, comment, synthetic_confirmed: confirmed }); setMessage('Feedback recorded. Thank you.'); setComment(''); setConfirmed(false); await refresh() }
        catch (reason) { setMessage(reason instanceof Error ? reason.message : 'Unable to save feedback') }
        finally { setBusy(false) }
      }}>
        <label>Reviewed job<select required value={jobId} onChange={e => setJobId(e.target.value)}><option value="">Choose a draft</option>{jobs.filter(job => job.draft).map(job => <option key={job.id} value={job.id}>#{shortId(job.id)} · {job.case_id ?? 'Synthetic draft'}</option>)}</select></label>
        <div className="rating-row">{[['Usability', usability, setUsability], ['Accuracy', accuracy, setAccuracy]].map(([label, value, setValue]) => <label key={String(label)}>{String(label)}<select required value={String(value)} onChange={e => (setValue as (value: string) => void)(e.target.value)}><option value="">Choose rating</option>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n} / 5</option>)}</select></label>)}</div>
        <label>Issue category<select value={issue} onChange={e => setIssue(e.target.value)}>{['none','omission','unsupported_claim','citation','workflow','other'].map(value => <option key={value} value={value}>{value.replace('_',' ')}</option>)}</select></label>
        <label>What should improve?<textarea value={comment} maxLength={2000} onChange={e => setComment(e.target.value)} rows={3} /></label>
        <label className="feedback-confirm"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />This feedback contains only synthetic case information.</label>
        <button className="primary" disabled={busy || !confirmed}>Record feedback</button>
      </form>}
      {message && <p role="status">{message}</p>}
    </section>
  </main>
}
