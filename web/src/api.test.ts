import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('API transport', () => {
  it('submits the selected connection without credentials in the payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'job' })))
    vi.stubGlobal('fetch', fetchMock)
    await api.createTranscript('Patient: A synthetic cough.', 'my-local-model')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs')
    expect(JSON.parse(init.body)).toEqual({ transcript: 'Patient: A synthetic cough.', synthetic: true, model_id: 'my-local-model' })
    expect(init.headers).not.toHaveProperty('X-API-Key')
    expect(init.headers).toHaveProperty('Idempotency-Key')
  })

  it('notifies the auth gate when a session expires', async () => {
    const dispatchEvent = vi.fn()
    vi.stubGlobal('window', { dispatchEvent })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'sign in required' }), { status: 401 })))
    await expect(api.listJobs()).rejects.toThrow('sign in required')
    expect(dispatchEvent.mock.calls[0][0].type).toBe('scribebench-session-expired')
  })
})
