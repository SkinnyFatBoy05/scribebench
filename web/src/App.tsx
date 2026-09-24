import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { api, type ModelConnection } from './api'
import { AuthGate } from './components/AuthGate'
import { JobProgress } from './components/JobProgress'
import { NotePanel } from './components/NotePanel'
import { Sidebar } from './components/Sidebar'
import { TranscriptPanel } from './components/TranscriptPanel'
import { CheckIcon, ExportIcon, ReviewIcon, TrashIcon } from './icons'
import { formatTime, humanStatus, shortId } from './lib'
import type { Draft, Job, SyntheticCase, ViewName } from './types'

const inProgress = new Set(['queued', 'running', 'retrying'])

function Header({ onNew }: { onNew: () => void }) {
  return (
    <header className="topbar">
      <div>
        <span className="scope-label">Synthetic cases only</span>
        <span className="boundary-label">Portfolio deployment</span>
      </div>
      <button type="button" className="primary small" onClick={onNew}>New transcript</button>
    </header>
  )
}

function EmptyReview({ onCases }: { onCases: () => void }) {
  return (
    <div className="empty-state">
      <ReviewIcon />
      <h1>No draft selected</h1>
      <p>Choose a synthetic case or submit a synthetic transcript to begin an evidence-linked review.</p>
      <button type="button" className="primary" onClick={onCases}>Open case library</button>
    </div>
  )
}

function ReviewWorkspace({
  job,
  onJobChange,
  onDeleted,
}: {
  job: Job
  onJobChange: (job: Job) => void
  onDeleted: (id: string) => void
}) {
  const [draft, setDraft] = useState<Draft | null>(job.draft)
  const [dirty, setDirty] = useState(false)
  const [focusedLine, setFocusedLine] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const focusLine = (line: number) => {
    setFocusedLine(line)
    document.getElementById(`line-${line}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const save = async () => {
    if (!draft) return
    setBusy(true)
    setMessage('')
    try {
      const updated = await api.saveDraft(job.id, draft)
      onJobChange(updated)
      setDirty(false)
      setMessage('Draft saved')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const approve = async () => {
    setBusy(true)
    setMessage('')
    try {
      let current = job
      if (dirty && draft) current = await api.saveDraft(job.id, draft)
      current = await api.approve(current.id)
      onJobChange(current)
      setDirty(false)
      setMessage('Draft approved. Export is now available.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Approval failed')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('Permanently delete this synthetic transcript and its draft?')) return
    setBusy(true)
    try {
      await api.deleteJob(job.id)
      onDeleted(job.id)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Delete failed')
      setBusy(false)
    }
  }

  const editable = ['draft_ready', 'under_review'].includes(job.status)

  return (
    <main className="review-view">
      <section className="review-heading">
        <div className="title-lockup">
          <span><ReviewIcon /></span>
          <div>
            <h1>Draft review</h1>
            <p>Compare every statement with the synthetic source before approval.</p>
          </div>
        </div>
        <div className="job-meta">
          <span>Job #{shortId(job.id)}</span>
          <span>{humanStatus(job.status)}</span>
          <span>{job.model_version}</span>
        </div>
        <JobProgress status={job.status} />
      </section>

      {inProgress.has(job.status) && (
        <div className="processing-state" role="status">
          <span className="spinner" />
          <div><strong>Generating grounded draft</strong><p>{humanStatus(job.status)} · attempt {job.attempts || 1}</p></div>
        </div>
      )}

      {job.status === 'failed' && (
        <div className="failure-state" role="alert">
          <strong>Draft generation failed safely</strong>
          <p>Error code: {job.error_code ?? 'unknown'}. No export was created. Start a new job after checking model availability.</p>
        </div>
      )}

      {draft && (
        <div className="review-grid">
          <TranscriptPanel transcript={job.transcript} draft={draft} focusedLine={focusedLine} onFocusLine={focusLine} />
          <NotePanel
            draft={draft}
            disabled={!editable}
            onFocusLine={focusLine}
            onChange={(next) => { setDraft(next); setDirty(true); setMessage('Unsaved changes') }}
          />
        </div>
      )}

      <footer className="action-bar">
        <div className="save-state">
          <span className={dirty ? 'unsaved-dot' : 'saved-dot'} />
          <span>{message || (job.status === 'approved' ? `Approved ${formatTime(job.approved_at!)}` : dirty ? 'Unsaved changes' : 'Draft version is saved')}</span>
        </div>
        <div className="action-buttons">
          <button type="button" className="icon-button danger" title="Delete synthetic case" onClick={remove} disabled={busy}><TrashIcon /></button>
          {editable && <button type="button" className="secondary" onClick={save} disabled={busy || !dirty}>Save edits</button>}
          <a className={`secondary export-link ${job.status !== 'approved' ? 'disabled' : ''}`} href={job.status === 'approved' ? api.exportUrl(job.id) : undefined} download>
            <ExportIcon /> Export JSON
          </a>
          {editable && <button type="button" className="primary" onClick={approve} disabled={busy || draft?.abstained}><CheckIcon />Approve draft</button>}
        </div>
      </footer>
    </main>
  )
}

function JobsView({ jobs, onOpen, onDelete }: { jobs: Job[]; onOpen: (job: Job) => void; onDelete: (job: Job) => void }) {
  return (
    <main className="list-view">
      <div className="page-heading"><div><h1>Jobs</h1><p>Durable processing history for synthetic transcripts.</p></div><span>{jobs.length} total</span></div>
      <div className="data-table" role="table" aria-label="Processing jobs">
        <div className="table-row table-head" role="row"><span>Job</span><span>Status</span><span>Model</span><span>Updated</span><span>Actions</span></div>
        {jobs.map((job) => (
          <div className="table-row" role="row" key={job.id}>
            <span><strong>#{shortId(job.id)}</strong><small>{job.case_id ?? 'Custom transcript'}</small></span>
            <span><i className={`status-chip ${job.status}`}>{humanStatus(job.status)}</i></span>
            <span className="mono-cell">{job.model_version}</span>
            <span>{formatTime(job.updated_at)}</span>
            <span className="row-actions"><button type="button" onClick={() => onOpen(job)}>Open review</button><button type="button" className="danger-text" onClick={() => onDelete(job)}>Delete</button></span>
          </div>
        ))}
      </div>
    </main>
  )
}

function CasesView({ cases, busy, onRun }: { cases: SyntheticCase[]; busy: boolean; onRun: (item: SyntheticCase) => void }) {
  return (
    <main className="list-view">
      <div className="page-heading"><div><h1>Case library</h1><p>Versioned synthetic scenarios split by family before variation.</p></div><span>{cases.length} fixtures</span></div>
      <div className="case-list">
        {cases.map((item) => (
          <article key={item.id}>
            <div><span className="split-label">{item.split}</span><h2>{item.title}</h2><p>{item.scenario_family} · {item.difficulty}</p></div>
            <button type="button" className="secondary" onClick={() => onRun(item)} disabled={busy}>Run case</button>
          </article>
        ))}
      </div>
    </main>
  )
}

function ExportsView({ jobs }: { jobs: Job[] }) {
  const approved = jobs.filter((job) => job.status === 'approved')
  return (
    <main className="list-view">
      <div className="page-heading"><div><h1>Exports</h1><p>Only human-approved draft versions are available.</p></div><span>{approved.length} approved</span></div>
      {approved.length === 0 ? <div className="plain-empty"><ExportIcon /><h2>No approved exports</h2><p>Complete a draft review and approve it first.</p></div> : (
        <div className="case-list">{approved.map((item) => <article key={item.id}><div><h2>Draft #{shortId(item.id)}</h2><p>{item.model_version} · approved {formatTime(item.approved_at!)}</p></div><a className="secondary export-link" href={api.exportUrl(item.id)} download><ExportIcon />Export JSON</a></article>)}</div>
      )}
    </main>
  )
}

function ConfigurationView({ jobs, models }: { jobs: Job[]; models: ModelConnection[] }) {
  const latest = jobs[0]
  const [connectionStatus, setConnectionStatus] = useState<Record<string, string>>({})
  const checkConnection = async (id: string) => {
    setConnectionStatus(current => ({ ...current, [id]: 'Checking…' }))
    try { const result = await api.checkModel(id); setConnectionStatus(current => ({ ...current, [id]: result.detail })) }
    catch { setConnectionStatus(current => ({ ...current, [id]: 'Connection check failed' })) }
  }
  return (
    <main className="list-view">
      <div className="page-heading"><div><h1>Model connections</h1><p>Select a connection above for new jobs. Existing drafts keep their original model attribution.</p></div></div>
      <div className="case-list">{models.map(model => <article key={model.id}><div><h2>{model.label}</h2><p>{model.model} · {model.provider}</p><p role="status">{connectionStatus[model.id]}</p></div><span>{model.external ? 'External · provider charges may apply' : model.provider === 'rule-based' ? 'Test baseline · not an LLM' : 'Self-hosted · no API charge'}</span><button className="secondary" onClick={() => checkConnection(model.id)}>Check connection</button></article>)}</div>
      <p className="connection-help">To attach a model, add an operator-owned connection to SCRIBE_MODELS_FILE and restart the API. Supports Ollama and OpenAI-compatible APIs (including gateways for other providers). Credentials are read from server environment variables, never returned to the browser. See docs/models.md for examples.</p>
      <dl className="configuration-list">
        <div><dt>Deployment boundary</dt><dd>Portfolio deployment · synthetic text only</dd></div>
        <div><dt>Most recent job model</dt><dd>{latest?.model_version ?? 'No jobs yet'}</dd></div>
        <div><dt>Storage</dt><dd>Durable SQLite with WAL and restart recovery</dd></div>
        <div><dt>Export policy</dt><dd>Human approval required</dd></div>
        <div><dt>Telemetry policy</dt><dd>Request metadata, latency, tokens and errors; no transcript logging</dd></div>
      </dl>
    </main>
  )
}

function NewTranscriptDialog({ onClose, onSubmit, busy }: { onClose: () => void; onSubmit: (transcript: string) => void; busy: boolean }) {
  const [transcript, setTranscript] = useState('Clinician: What brings you in today?\nPatient: I have had a dry cough for five days.\nClinician: Any fever?\nPatient: No fever.\nClinician: Do you take any medication?\nPatient: No regular medication.\nClinician: Any medication allergies?\nPatient: No known medication allergies.')
  const [confirmed, setConfirmed] = useState(false)
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="new-transcript-title" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><h2 id="new-transcript-title">New synthetic transcript</h2><p>Use speaker labels in the form “Clinician:” and “Patient:”.</p></div><button type="button" onClick={onClose} aria-label="Close">×</button></header>
        <label className="transcript-input">Transcript<textarea rows={12} value={transcript} onChange={(event) => setTranscript(event.target.value)} /></label>
        <label className="confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>I confirm this is entirely synthetic and contains no real patient data.</span></label>
        <footer><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="button" className="primary" disabled={!confirmed || transcript.trim().length < 20 || busy} onClick={() => onSubmit(transcript)}>Generate draft</button></footer>
      </section>
    </div>
  )
}

function App() {
  const [models, setModels] = useState<ModelConnection[]>([])
  const [modelId, setModelId] = useState('default')
  const [view, setView] = useState<ViewName>('review')
  const [jobs, setJobs] = useState<Job[]>([])
  const [cases, setCases] = useState<SyntheticCase[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const selected = useMemo(() => jobs.find((job) => job.id === selectedId) ?? null, [jobs, selectedId])

  useEffect(() => {
    Promise.all([api.listJobs(), api.listCases(), api.models()])
      .then(([loadedJobs, loadedCases, loadedModels]) => {
        setModels(loadedModels)
        setJobs(loadedJobs)
        setCases(loadedCases)
        if (loadedJobs[0]) setSelectedId(loadedJobs[0].id)
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load workspace'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected || !inProgress.has(selected.status)) return
    const timer = window.setInterval(() => {
      api.getJob(selected.id).then((updated) => {
        setJobs((current) => current.map((job) => job.id === updated.id ? updated : job))
      }).catch(() => undefined)
    }, 800)
    return () => window.clearInterval(timer)
  }, [selected])

  const replaceJob = (updated: Job) => {
    setJobs((current) => [updated, ...current.filter((job) => job.id !== updated.id)])
    setSelectedId(updated.id)
  }

  const runCase = async (item: SyntheticCase) => {
    setBusy(true); setError('')
    try {
      if (models.find(m => m.id === modelId)?.external && !window.confirm('Send this synthetic transcript to the selected external provider? API charges may apply.')) return
      const job = await api.createJob(item, modelId)
      replaceJob(job); setView('review')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create job')
    } finally { setBusy(false) }
  }

  const submitTranscript = async (transcript: string) => {
    setBusy(true); setError('')
    try {
      if (models.find(m => m.id === modelId)?.external && !window.confirm('Send this synthetic transcript to the selected external provider? API charges may apply.')) return
      const job = await api.createTranscript(transcript, modelId)
      replaceJob(job); setView('review'); setDialogOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create job')
    } finally { setBusy(false) }
  }

  const removeJob = async (job: Job) => {
    if (!window.confirm('Permanently delete this synthetic transcript and its draft?')) return
    try {
      await api.deleteJob(job.id)
      setJobs((current) => current.filter((item) => item.id !== job.id))
      if (selectedId === job.id) setSelectedId(null)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Delete failed') }
  }

  const openJob = (job: Job) => { setSelectedId(job.id); setView('review') }

  return (
    <div className="app-shell">
      <Sidebar view={view} onChange={setView} />
      <div className="app-main">
        <Header onNew={() => setDialogOpen(true)} />
        <div className="model-bar"><label htmlFor="model-select">Model for new jobs</label><select id="model-select" value={modelId} onChange={e => setModelId(e.target.value)}>{models.map(model => <option key={model.id} value={model.id}>{model.label} · {model.model}</option>)}</select><span>{models.find(m => m.id === modelId)?.external ? 'External provider · charges may apply' : 'Local inference · no API charge'}</span></div>
        {error && <div className="global-error" role="alert">{error}<button type="button" onClick={() => setError('')}>Dismiss</button></div>}
        {loading ? <div className="loading-page"><span className="spinner" />Loading workspace…</div> : (
          <>
            {view === 'review' && (selected ? <ReviewWorkspace key={`${selected.id}-${selected.draft ? 'ready' : 'pending'}`} job={selected} onJobChange={replaceJob} onDeleted={(id) => { setJobs((current) => current.filter((item) => item.id !== id)); setSelectedId(null) }} /> : <EmptyReview onCases={() => setView('cases')} />)}
            {view === 'jobs' && <JobsView jobs={jobs} onOpen={openJob} onDelete={removeJob} />}
            {view === 'cases' && <CasesView cases={cases} busy={busy} onRun={runCase} />}
            {view === 'exports' && <ExportsView jobs={jobs} />}
            {view === 'configuration' && <ConfigurationView jobs={jobs} models={models} />}
          </>
        )}
      </div>
      {dialogOpen && <NewTranscriptDialog onClose={() => setDialogOpen(false)} onSubmit={submitTranscript} busy={busy} />}
    </div>
  )
}

export default function AuthenticatedApp() { return <AuthGate><App /></AuthGate> }
