import { ExportIcon, JobsIcon, LibraryIcon, ReviewIcon, SettingsIcon } from '../icons'
import type { ViewName } from '../types'

const navigation = [
  { id: 'review', label: 'Review', Icon: ReviewIcon },
  { id: 'jobs', label: 'Jobs', Icon: JobsIcon },
  { id: 'cases', label: 'Case library', Icon: LibraryIcon },
  { id: 'exports', label: 'Exports', Icon: ExportIcon },
  { id: 'pilot', label: 'Pilot & operations', Icon: JobsIcon },
  { id: 'configuration', label: 'Configuration', Icon: SettingsIcon },
] as const

interface Props {
  view: ViewName
  onChange: (view: ViewName) => void
}

export function Sidebar({ view, onChange }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <span className="brand-mark">S</span>
        <div>
          <strong>ScribeBench</strong>
          <span>Synthetic only</span>
        </div>
      </div>
      <nav aria-label="Workspace">
        {navigation.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className={view === id ? 'nav-item active' : 'nav-item'}
            onClick={() => onChange(id)}
            aria-current={view === id ? 'page' : undefined}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div><span className="cube" />Synthetic workspace</div>
        <span>Local-first · human-reviewed</span>
      </div>
    </aside>
  )
}
