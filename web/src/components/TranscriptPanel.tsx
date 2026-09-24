import { AlertIcon, ArrowIcon } from '../icons'
import { splitTranscript } from '../lib'
import type { Draft } from '../types'

interface Props {
  transcript: string
  draft: Draft | null
  focusedLine: number | null
  onFocusLine: (line: number) => void
}

export function TranscriptPanel({ transcript, draft, focusedLine, onFocusLine }: Props) {
  const lines = splitTranscript(transcript)
  const contradictionLines = new Set(draft?.contradictions.flatMap((item) => item.lines) ?? [])
  const evidenceLines = new Set(
    draft
      ? [draft.reason_for_visit, draft.history, draft.observations].flatMap((section) => section.evidence.map((item) => item.line))
      : [],
  )

  return (
    <section className="workspace-panel transcript-panel" aria-labelledby="transcript-title">
      <header className="panel-header">
        <div>
          <p className="panel-kicker">Source</p>
          <h2 id="transcript-title">Conversation transcript</h2>
        </div>
        <span className="line-count">{lines.length} lines</span>
      </header>
      <div className="transcript-lines" aria-label="Synthetic conversation">
        {lines.map((line) => (
          <button
            type="button"
            key={line.number}
            id={`line-${line.number}`}
            className={`transcript-line ${focusedLine === line.number ? 'focused' : ''} ${contradictionLines.has(line.number) ? 'contradiction-line' : ''}`}
            onClick={() => onFocusLine(line.number)}
          >
            <span className="line-number">{String(line.number).padStart(2, '0')}</span>
            <strong>{line.speaker}</strong>
            <span>{line.text}</span>
            {evidenceLines.has(line.number) && <span className="evidence-dot" aria-label="Cited as evidence" />}
          </button>
        ))}
      </div>
      {!!draft?.contradictions.length && (
        <div className="alert contradiction-alert">
          <AlertIcon />
          <div>
            <strong>Contradiction detected</strong>
            <p>{draft.contradictions[0].summary}</p>
          </div>
          <button type="button" onClick={() => onFocusLine(draft.contradictions[0].lines[0])}>
            View lines <ArrowIcon />
          </button>
        </div>
      )}
    </section>
  )
}

