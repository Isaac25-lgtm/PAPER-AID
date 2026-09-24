import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiSource, POLL_MS } from './api-source'
import type { Job, PublicConfig } from './types'

const config = {} as PublicConfig
const job = (status: Job['status']) => ({ id: 'job_abc', status }) as Job
const reply = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

describe('watchJob', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('keeps polling through a temporary error and never reports the job missing', async () => {
    const responses = [reply(200, job('PROCESSING')), reply(503, { message: 'restarting' }), reply(200, job('COMPLETED'))]
    vi.stubGlobal('fetch', vi.fn(() => responses.shift()))
    const seen: (string | null)[] = []
    createApiSource({ config, getAuthHeaders: async () => ({ Authorization: 'Dev a@b.co' }) }).watchJob('job_abc', (j) => seen.push(j?.status ?? null))

    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(POLL_MS) // 503: backs off
    await vi.advanceTimersByTimeAsync(POLL_MS * 4)
    expect(seen).toEqual(['PROCESSING', 'COMPLETED'])
  })

  it('reports a 404 as missing and stops', async () => {
    const fetch = vi.fn(() => reply(404, { message: 'not found' }))
    vi.stubGlobal('fetch', fetch)
    const seen: (Job | null)[] = []
    createApiSource({ config, getAuthHeaders: async () => ({}) }).watchJob('job_abc', (j) => seen.push(j))

    await vi.advanceTimersByTimeAsync(POLL_MS * 10)
    expect(seen).toEqual([null])
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('stops polling once the job is finished or the page unsubscribes', async () => {
    const fetch = vi.fn(() => reply(200, job('PROCESSING')))
    vi.stubGlobal('fetch', fetch)
    const stop = createApiSource({ config, getAuthHeaders: async () => ({}) }).watchJob('job_abc', () => {})

    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    stop()
    const calls = fetch.mock.calls.length
    await vi.advanceTimersByTimeAsync(POLL_MS * 10)
    expect(fetch.mock.calls.length).toBe(calls)
  })
})

describe('requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('send the identity header and surface the server message and status', async () => {
    const fetch = vi.fn((_url: string, _init?: RequestInit) => reply(409, { message: 'Your quote changed.' }))
    vi.stubGlobal('fetch', fetch)
    const source = createApiSource({ config, getAuthHeaders: async () => ({ Authorization: 'Dev a@b.co' }) })

    await expect(source.submitJob('job_abc', 'quote_1')).rejects.toMatchObject({ message: 'Your quote changed.', status: 409 })
    expect((fetch.mock.calls[0][1]?.headers as Record<string, string>).Authorization).toBe('Dev a@b.co')
  })
})
