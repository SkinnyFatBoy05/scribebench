export type JobStatus =
  | 'queued'
  | 'running'
  | 'retrying'
  | 'draft_ready'
  | 'under_review'
  | 'approved'
  | 'failed'

export interface Evidence {
  line: number
  quote: string
}

export interface NoteSection {
  text: string
  evidence: Evidence[]
}

export interface Draft {
  reason_for_visit: NoteSection
  history: NoteSection
  observations: NoteSection
  missing_information: Array<{ field: string; reason: string }>
  contradictions: Array<{ summary: string; lines: number[] }>
  warnings: string[]
  abstained: boolean
}

export interface Job {
  id: string
  case_id: string | null
  transcript: string
  transcript_sha256: string
  status: JobStatus
  model_version: string
  attempts: number
  draft: Draft | null
  error_code: string | null
  created_at: string
  updated_at: string
  approved_at: string | null
  latency_ms: number | null
  input_tokens: number
  output_tokens: number
}

export interface SyntheticCase {
  id: string
  title: string
  scenario_family: string
  split: 'train' | 'validation' | 'test'
  difficulty: string
  transcript: string
  expected: Record<string, unknown>
}

export type ViewName = 'review' | 'jobs' | 'cases' | 'exports' | 'configuration' | 'pilot'
