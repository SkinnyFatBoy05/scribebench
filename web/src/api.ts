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
    if (response.status === 401) window.dispatchEvent(new Event('scribebench-session-expired'))
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
  session: () => request<{ authenticated: boolean; required: boolean }>('/api/auth/session'),
  login: (key: string) => request('/api/auth/login', { method: 'POST', body: JSON.stringify({ key }) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  models: () => request<ModelConnection[]>('/api/models'),
  checkModel: (id: string) => request<{ available: boolean; detail: string }>(`/api/models/${encodeURIComponent(id)}/check`),
  listCases: () => request<SyntheticCase[]>('/api/cases'),
  listJobs: () => request<Job[]>('/api/jobs'),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (syntheticCase: SyntheticCase, modelId = 'default') =>
    request<Job>('/api/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `case-${syntheticCase.id}-${crypto.randomUUID()}` },
      body: JSON.stringify({
        transcript: syntheticCase.transcript,
        synthetic: true,
        case_id: syntheticCase.id,
        model_id: modelId,
      }),
    }),
  createTranscript: (transcript: string, modelId = 'default') =>
    request<Job>('/api/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `transcript-${crypto.randomUUID()}` },
      body: JSON.stringify({ transcript, synthetic: true, model_id: modelId }),
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

export type ModelConnection = { id: string; label: string; provider: string; model: string; external: boolean; version: string }
