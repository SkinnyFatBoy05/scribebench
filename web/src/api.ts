import type { Draft, Job, SyntheticCase } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': crypto.randomUUID(),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = body.detail ?? message
    } catch {
      // Keep the status-based message for non-JSON proxy failures.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  listCases: () => request<SyntheticCase[]>('/api/cases'),
  listJobs: () => request<Job[]>('/api/jobs'),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (syntheticCase: SyntheticCase) =>
    request<Job>('/api/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `case-${syntheticCase.id}-${crypto.randomUUID()}` },
      body: JSON.stringify({
        transcript: syntheticCase.transcript,
        synthetic: true,
        case_id: syntheticCase.id,
      }),
    }),
  createTranscript: (transcript: string) =>
    request<Job>('/api/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `transcript-${crypto.randomUUID()}` },
      body: JSON.stringify({ transcript, synthetic: true }),
    }),
  saveDraft: (id: string, draft: Draft) =>
    request<Job>(`/api/jobs/${id}/draft`, {
      method: 'PATCH',
      body: JSON.stringify({ draft }),
    }),
  approve: (id: string) => request<Job>(`/api/jobs/${id}/approve`, { method: 'POST' }),
  deleteJob: async (id: string) => {
    const response = await fetch(`/api/jobs/${id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error(`Delete failed (${response.status})`)
  },
  exportUrl: (id: string) => `/api/jobs/${id}/export`,
}
