import { AlertIcon } from '../icons'
import type { Draft, NoteSection } from '../types'

interface Props {
  draft: Draft
  disabled: boolean
  onChange: (draft: Draft) => void
  onFocusLine: (line: number) => void
}

function SectionEditor({
  label,
  section,
  disabled,
  rows,
  placeholder,
  onChange,
  onFocusLine,
}: {
  label: string
  section: NoteSection
  disabled: boolean
  rows: number
  placeholder: string
  onChange: (section: NoteSection) => void
  onFocusLine: (line: number) => void
}) {
  return (
    <div className="note-section">
      <label>{label}</label>
      <textarea
        aria-label={label}
        value={section.text}
        disabled={disabled}
        rows={rows}
        placeholder={placeholder}
        onChange={(event) => onChange({ ...section, text: event.target.value })}
      />
      {!!section.evidence.length && (
        <div className="citations" aria-label={`${label} evidence`}>
          {section.evidence.map((citation) => (
            <button
              type="button"
              key={`${citation.line}-${citation.quote}`}
              title={citation.quote}
              onClick={() => onFocusLine(citation.line)}
            >
              L{citation.line}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function NotePanel({ draft, disabled, onChange, onFocusLine }: Props) {
  const update = (key: 'reason_for_visit' | 'history' | 'observations', section: NoteSection) => {
    onChange({ ...draft, [key]: section })
  }
  return (
    <section className="workspace-panel note-panel" aria-labelledby="draft-title">
      <header className="panel-header">
        <div>
          <p className="panel-kicker">Human review required</p>
          <h2 id="draft-title">Structured note <span>(draft)</span></h2>
        </div>
        {draft.abstained && <span className="status-chip failed">Abstained</span>}
      </header>
      {draft.warnings.map((warning) => (
        <div className="inline-warning" key={warning}><AlertIcon />{warning}</div>
      ))}
      <SectionEditor
        label="Reason for visit"
        section={draft.reason_for_visit}
        disabled={disabled}
        rows={2}
        placeholder="No supported reason for visit was extracted."
        onChange={(section) => update('reason_for_visit', section)}
        onFocusLine={onFocusLine}
      />
      <SectionEditor
        label="History"
        section={draft.history}
        disabled={disabled}
        rows={5}
        placeholder="No supported history was extracted."
        onChange={(section) => update('history', section)}
        onFocusLine={onFocusLine}
      />
      <SectionEditor
        label="Observations"
        section={draft.observations}
        disabled={disabled}
        rows={3}
        placeholder="No objective observations were stated in the transcript."
        onChange={(section) => update('observations', section)}
        onFocusLine={onFocusLine}
      />
      {!!draft.missing_information.length && (
        <section className="missing-block" aria-labelledby="missing-title">
          <h3 id="missing-title"><AlertIcon />Missing information</h3>
          <ul>
            {draft.missing_information.map((item) => (
              <li key={item.field}><strong>{item.field}</strong><span>{item.reason}</span></li>
            ))}
          </ul>
        </section>
      )}
      <section className="evidence-index" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Evidence</h3>
        {[draft.reason_for_visit, draft.history, draft.observations]
          .flatMap((section) => section.evidence)
          .filter((citation, index, items) => items.findIndex((item) => item.line === citation.line) === index)
          .map((citation) => (
            <button type="button" key={citation.line} onClick={() => onFocusLine(citation.line)}>
              <span>L{citation.line}</span><p>{citation.quote}</p><strong>Go to line</strong>
            </button>
          ))}
      </section>
    </section>
  )
}
