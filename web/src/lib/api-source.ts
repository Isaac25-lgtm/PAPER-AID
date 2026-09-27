// DataSource backed by the PaperAid API. Identity comes from `getAuthHeader`, which the auth layer
// supplies (a Firebase ID token in production, a local developer identity when running locally).
import { DataError, type DataSource, type JobQuery } from './data'
import type { AdminJob, AdminSummary, FileMeta, Job, Page, PublicConfig, QuoteResponse, Wallet, WalletSummary } from './types'

interface Options {
  config: PublicConfig
  getAuthHeaders: () => Promise<Record<string, string>>
}

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])
export const POLL_MS = 2000

/** Parses a response body that should be JSON; an HTML error page (a proxy's 413 or 502) is null. */
function parseJson<T>(text: string): T | null {
  try {
    return JSON.parse(text || 'null') as T
  } catch (e) {
    if (e instanceof SyntaxError) return null
    throw e
  }
}

const UPLOAD_TIMEOUT_MS = 5 * 60_000

/** Public settings. Sent with the visitor's credentials when signed in, because which services a
 *  visitor may use can depend on who they are (invited testers). */
export async function fetchPublicConfig(headers: Record<string, string> = {}): Promise<PublicConfig> {
  const res = await fetch('/api/config', { headers })
  if (!res.ok) throw new DataError('PaperAid is unavailable right now. Please try again shortly.')
  return (await res.json()) as PublicConfig
}

function query(params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== '' && value !== 'ALL') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function createApiSource({ config, getAuthHeaders }: Options): DataSource {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let res: Response
    try {
      res = await fetch(path, { ...init, headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(await getAuthHeaders()), ...init.headers } })
    } catch {
      throw new DataError('We could not reach PaperAid. Check your connection and try again.')
    }
    if (res.status === 204) return undefined as T
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new DataError((body as { message?: string } | null)?.message ?? 'Something went wrong. Please try again.', res.status)
    return body as T
  }

  return {
    config,

    listJobs: (q: JobQuery) =>
      request<Page<Job>>(`/api/jobs${query({ status: q.status, service: q.service, cursor: q.cursor, limit: q.limit })}`),

    getJob: (jobId) =>
      request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`).catch((err: unknown) => {
        if (err instanceof DataError && err.status === 404) return null
        throw err
      }),

    watchJob(jobId, onChange, onBlocked) {
      let stopped = false
      let failures = 0
      let timer: ReturnType<typeof setTimeout>
      const tick = async () => {
        try {
          const job = await request<Job>(`/api/jobs/${jobId}`)
          if (stopped) return
          failures = 0
          onChange(job)
          if (!TERMINAL.has(job.status)) timer = setTimeout(tick, POLL_MS)
        } catch (err) {
          if (stopped) return
          if (err instanceof DataError && err.status === 404) return onChange(null) // truly missing, or not yours
          if (err instanceof DataError && (err.status === 401 || err.status === 403)) return onBlocked?.(err.message) // retrying won't help
          failures += 1 // a blip (network, restart, 5xx): keep the last known state and try again
          timer = setTimeout(tick, Math.min(POLL_MS * 2 ** failures, 15_000))
        }
      }
      tick()
      return () => {
        stopped = true
        clearTimeout(timer)
      }
    },

    createDraft: async () => (await request<{ id: string }>('/api/jobs', { method: 'POST' })).id,

    async uploadFile(draftId, role, file, onProgress) {
      const headers = await getAuthHeaders()
      return new Promise<FileMeta>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `/api/jobs/${draftId}/files/${role}`)
        for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v)
        xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 95))
        xhr.timeout = UPLOAD_TIMEOUT_MS
        xhr.onerror = () => reject(new DataError('The upload failed. Check your connection and try again.'))
        xhr.ontimeout = () => reject(new DataError('The upload took too long. Check your connection and try again.'))
        xhr.onabort = () => reject(new DataError('The upload was interrupted. Try again.'))
        xhr.onload = () => {
          const body = parseJson<FileMeta & { message?: string }>(xhr.responseText)
          if (xhr.status >= 200 && xhr.status < 300 && body) {
            onProgress(100)
            resolve(body)
          } else
            reject(
              new DataError(
                body?.message ?? (xhr.status === 413 ? 'This file is too large to upload.' : 'The upload failed. Try again in a moment.'),
                xhr.status,
              ),
            )
        }
        const form = new FormData()
        form.append('file', file)
        xhr.send(form)
      })
    },

    requestQuote: (draftId, selection, startEstimate = false) =>
      request<QuoteResponse>(`/api/jobs/${draftId}/quote`, { method: 'POST', body: JSON.stringify({ selection, startEstimate }) }),

    getWallet: () => request<Wallet>('/api/wallet'),

    submitJob: async (draftId, quoteId) =>
      (await request<Job>(`/api/jobs/${draftId}/submit`, { method: 'POST', body: JSON.stringify({ quoteId }) })).id,

    cancelJob: async (jobId) => {
      await request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
    },

    removeGuideline: (draftId) => request<void>(`/api/jobs/${draftId}/files/guideline`, { method: 'DELETE' }),

    deleteJob: (jobId) => request<void>(`/api/jobs/${jobId}`, { method: 'DELETE' }),

    deleteAccount: () => request<void>('/api/me', { method: 'DELETE' }),

    async download(jobId, outputId, fileName) {
      const res = await fetch(`/api/jobs/${jobId}/outputs/${outputId}`, { headers: await getAuthHeaders() })
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { message?: string } | null
        throw new DataError(body?.message ?? 'This file is not available.', res.status)
      }
      const link = document.createElement('a')
      if (res.headers.get('content-type')?.includes('application/json')) {
        // Production: a short-lived signed link. Navigating to it needs no CORS, unlike fetch().
        link.href = ((await res.json()) as { url: string }).url
      } else {
        const url = URL.createObjectURL(await res.blob())
        link.href = url
        link.download = fileName
        setTimeout(() => URL.revokeObjectURL(url), 5000)
      }
      document.body.appendChild(link)
      link.click()
      link.remove()
    },

    admin: {
      summary: () => request<AdminSummary>('/api/admin/summary'),
      listJobs: (q) =>
        request<Page<AdminJob>>(`/api/admin/jobs${query({ status: q.status, service: q.service, search: q.search, cursor: q.cursor, limit: q.limit })}`),
      getJob: (jobId) => request<AdminJob>(`/api/admin/jobs/${jobId}`).catch(() => null),
      retryJob: async (jobId) => {
        await request<AdminJob>(`/api/admin/jobs/${jobId}/retry`, { method: 'POST' })
      },
      cancelJob: async (jobId) => {
        await request<AdminJob>(`/api/admin/jobs/${jobId}/cancel`, { method: 'POST' })
      },
      setProcessing: async (enabled) => {
        await request<{ processingEnabled: boolean }>('/api/admin/processing', { method: 'POST', body: JSON.stringify({ enabled }) })
      },
      listWallets: (search) => request<WalletSummary[]>(`/api/admin/wallets${query({ search })}`),
      grantCredits: (email, amount, note, opId) =>
        request<WalletSummary>('/api/admin/credits', { method: 'POST', body: JSON.stringify({ email, amount, note, opId }) }),
    },
  }
}
