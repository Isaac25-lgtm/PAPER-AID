// DataSource backed by the PaperAid API. Identity comes from `getAuthHeader`, which the auth layer
// supplies (a Firebase ID token in production, a local developer identity when running locally).
import { DataError, type DataSource, type JobQuery, type Notifications } from './data'
import type { ChapterView, Comparison, EvidenceItem, Project, Rulebook, StepQuote } from './proposal-types'
import type { AnalysisResult, DataPreview, DataProject, IdentifierRules, Places, ReportDocument } from './datalab-types'
import type { Work, WorkDocumentView, WorkStepQuote } from './work-types'
import type { AdminJob, AdminSummary, FileMeta, ImageMeta, Job, JobDocument, LedgerEntry, Page, PublicConfig, QuoteResponse, Wallet, WalletSummary } from './types'

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

/** Opens the terms dialog (`TermsDialog`) and resolves once the person accepts (true) or closes it (false). */
export function termsAccepted(): Promise<boolean> {
  return new Promise((resolve) => {
    // The dialog claims the request (preventDefault); with no dialog on the page the step fails as before.
    const taken = !window.dispatchEvent(new CustomEvent<TermsAsk>('paperaid:terms', { detail: { resolve }, cancelable: true }))
    if (!taken) resolve(false)
  })
}

export type TermsAsk = { resolve: (accepted: boolean) => void }

function query(params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== '' && value !== 'ALL') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function createApiSource({ config, getAuthHeaders }: Options): DataSource {
  async function request<T>(path: string, init: RequestInit = {}, askedForTerms = false): Promise<T> {
    let res: Response
    try {
      res = await fetch(path, { ...init, headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(await getAuthHeaders()), ...init.headers } })
    } catch {
      throw new DataError('We could not reach PaperAid. Check your connection and try again.')
    }
    if (res.status === 204) return undefined as T
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      const { message, code } = (body ?? {}) as { message?: string; code?: string }
      // The step waits while the terms dialog asks; once they are accepted it goes ahead by itself (owner, 2026-10-07).
      // The server refused it before doing anything, so sending it again is safe.
      if (code === 'TERMS_REQUIRED' && !askedForTerms && (await termsAccepted())) return request<T>(path, init, true)
      throw new DataError(message ?? 'Something went wrong. Please try again.', res.status, code)
    }
    return body as T
  }

  /** A Word file built on request: fetched with the student's credentials and saved by the browser. */
  /** `fileName` without an extension takes it from the file's type (the cleaned data is Excel, or CSV when large). */
  async function saveFile(path: string, fileName: string): Promise<void> {
    const res = await fetch(path, { headers: await getAuthHeaders() })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null
      throw new DataError(body?.message ?? 'The document could not be prepared.', res.status)
    }
    const typed = /\.[a-z0-9]{2,4}$/i.test(fileName) ? fileName : fileName + ((res.headers.get('content-type') ?? '').includes('csv') ? '.csv' : '.xlsx')
    const url = URL.createObjectURL(await res.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = typed
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  }

  async function blob(path: string): Promise<Blob> {
    const res = await fetch(path, { headers: await getAuthHeaders() })
    if (!res.ok) throw new DataError('This could not be loaded.', res.status)
    return res.blob()
  }

  function withDocument(fields: Record<string, string>, file: File) {
    const form = new FormData()
    for (const [k, v] of Object.entries(fields)) form.append(k, v)
    form.append('file', file)
    return form
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
    walletHistory: (before) => request<{ entries: LedgerEntry[]; next: string | null }>(`/api/wallet/history${query({ before })}`),

    submitJob: async (draftId, quoteId) =>
      (await request<Job>(`/api/jobs/${draftId}/submit`, { method: 'POST', body: JSON.stringify({ quoteId }) })).id,

    cancelJob: async (jobId) => {
      await request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
    },

    removeGuideline: (draftId) => request<void>(`/api/jobs/${draftId}/files/guideline`, { method: 'DELETE' }),

    async uploadLogo(draftId, file) {
      const form = new FormData()
      form.append('file', file)
      return request<ImageMeta>(`/api/jobs/${draftId}/files/logo`, { method: 'POST', body: form })
    },

    removeLogo: (draftId) => request<void>(`/api/jobs/${draftId}/files/logo`, { method: 'DELETE' }),

    deleteJob: (jobId) => request<void>(`/api/jobs/${jobId}`, { method: 'DELETE' }),

    deleteAccount: () => request<void>('/api/me', { method: 'DELETE' }),
    acceptTerms: (version) => request<void>('/api/me/terms', { method: 'POST', body: JSON.stringify({ version }) }),
    notifications: () => request<Notifications>('/api/me/notifications'),
    setNotifications: (choice) => request<Notifications>('/api/me/notifications', { method: 'POST', body: JSON.stringify(choice) }),

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

    workspace: {
      document: (jobId) => request<JobDocument>(`/api/jobs/${jobId}/document`),
      setFinding: (jobId, findingId, dismissed) => request<Job>(`/api/jobs/${jobId}/findings/${findingId}`, { method: 'POST', body: JSON.stringify({ dismissed }) }),
      setChange: (jobId, changeId, accepted) => request<Job>(`/api/jobs/${jobId}/changes/${changeId}`, { method: 'POST', body: JSON.stringify({ accepted }) }),
      rebuild: (jobId) => request<Job>(`/api/jobs/${jobId}/rebuild`, { method: 'POST' }),
      fix: (jobId, findingIds, safeOnly) => request<Job>(`/api/jobs/${jobId}/fix`, { method: 'POST', body: JSON.stringify({ findingIds, safeOnly }) }),
      continueFrom: (jobId, origin, instruction = '', blocks = []) =>
        request<Job>(`/api/jobs/${jobId}/continue`, { method: 'POST', body: JSON.stringify({ origin, instruction, blocks }) }),
    },

    projects: {
      rulebook: () => request<Rulebook>('/api/projects/rulebook'),
      list: () => request<Project[]>('/api/projects'),
      get: (id) =>
        request<Project>(`/api/projects/${encodeURIComponent(id)}`).catch((err: unknown) => {
          if (err instanceof DataError && err.status === 404) return null
          throw err
        }),
      create: (inputs, titlePage, citation, goal = 'FULL') => request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ inputs, titlePage, citation, goal }) }),
      continueToFull: (id) => request<Project>(`/api/projects/${id}/continue`, { method: 'POST' }),
      answerGuide: (id, departureId, answer) =>
        request<Project>(`/api/projects/${id}/guide-answers`, { method: 'POST', body: JSON.stringify({ id: departureId, answer }) }),
      updateDetails: (id, inputs, titlePage, citation) =>
        request<Project>(`/api/projects/${id}/details`, { method: 'POST', body: JSON.stringify({ inputs, titlePage, citation }) }),
      savePlan: (id, plan, baseVersion) => request<Project>(`/api/projects/${id}/plan`, { method: 'POST', body: JSON.stringify({ plan, baseVersion }) }),
      approvePlan: (id, baseVersion, acknowledge = []) => request<Project>(`/api/projects/${id}/plan/approve`, { method: 'POST', body: JSON.stringify({ baseVersion, acknowledge }) }),
      takeCandidate: (id, accept) => request<Project>(`/api/projects/${id}/plan/candidate`, { method: 'POST', body: JSON.stringify({ accept }) }),
      sampleSize: (id, sample) => request<{ size: number | null; steps: string; missing: string }>(`/api/projects/${id}/sample-size`, { method: 'POST', body: JSON.stringify(sample) }),
      quoteStep: (id, step, note, comments) => request<StepQuote>(`/api/projects/${id}/steps`, { method: 'POST', body: JSON.stringify({ step, note, comments: comments ?? [] }) }),
      submitStep: async (id, jobId, quoteId) => {
        await request<Job>(`/api/projects/${id}/steps/${jobId}/submit`, { method: 'POST', body: JSON.stringify({ quoteId }) })
      },
      chapter: (id, number, version) => request<ChapterView>(`/api/projects/${id}/chapters/${number}${query({ version })}`),
      setChapter: (id, number, version, approved) =>
        request<Project>(`/api/projects/${id}/chapters/${number}`, { method: 'POST', body: JSON.stringify({ version, approved }) }),
      evidence: (id) => request<EvidenceItem[]>(`/api/projects/${id}/evidence`),
      download: (id, final, fileName) => saveFile(`/api/projects/${id}/export${query({ final: final ? 'true' : null })}`, fileName),
      downloadPdf: (id, final, fileName) => saveFile(`/api/projects/${id}/export.pdf${query({ final: final ? 'true' : null })}`, fileName),
      downloadLatex: (id, final, fileName) => saveFile(`/api/projects/${id}/export.zip${query({ final: final ? 'true' : null })}`, fileName),
      remove: (id) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
      compare: (id, number, older, newer) => request<Comparison>(`/api/projects/${id}/chapters/${number}/compare${query({ older, newer })}`),
      addFeedback: (id, text) => request<Project>(`/api/projects/${id}/feedback`, { method: 'POST', body: JSON.stringify({ text }) }),
      addFeedbackFile(id, file) {
        const form = new FormData()
        form.append('file', file)
        return request<Project>(`/api/projects/${id}/feedback/file`, { method: 'POST', body: form })
      },
      editFeedback: (id, commentId, edit) => request<Project>(`/api/projects/${id}/feedback/${commentId}`, { method: 'POST', body: JSON.stringify(edit) }),
      deleteFeedback: (id, commentId) => request<Project>(`/api/projects/${id}/feedback/${commentId}`, { method: 'DELETE' }),
      downloadResponse: (id) => saveFile(`/api/projects/${id}/feedback/report`, 'Response to supervisor comments.docx'),
      downloadConcept: (id, fileName) => saveFile(`/api/projects/${id}/concept/export`, fileName),
      requestChanges: (id, chapter, instruction, sections) =>
        request<Project>(`/api/projects/${id}/chapters/${chapter}/request`, { method: 'POST', body: JSON.stringify({ instruction, sections }) }),
      requestChangesWithDocument: (id, chapter, instruction, sections, file) =>
        request<Project>(`/api/projects/${id}/chapters/${chapter}/request/with-document`, { method: 'POST', body: withDocument({ instruction, sections: sections.join(',') }, file) }),
      start: (id, acceptSampling = false) => request<Project>(`/api/projects/${id}/start`, { method: 'POST', body: JSON.stringify({ acceptSampling }) }),
      framework: (id) => blob(`/api/projects/${id}/framework.png`),
      uploadGuide(id, file) {
        const form = new FormData()
        form.append('file', file)
        return request<Project>(`/api/projects/${id}/guide`, { method: 'POST', body: form })
      },
      useDefaultRulebook: (id) => request<Project>(`/api/projects/${id}/rulebook/default`, { method: 'POST' }),
    },

    works: {
      list: () => request<Work[]>('/api/works'),
      get: (id) =>
        request<Work>(`/api/works/${encodeURIComponent(id)}`).catch((err: unknown) => {
          if (err instanceof DataError && err.status === 404) return null
          throw err
        }),
      create: (kind, variant, mode, inputs, citation) => request<Work>('/api/works', { method: 'POST', body: JSON.stringify({ kind, variant, mode, inputs, citation }) }),
      updateDetails: (id, inputs, change, baseVersion) =>
        request<Work>(`/api/works/${id}/details`, { method: 'POST', body: JSON.stringify({ inputs, ...change, baseVersion }) }),
      answer: (id, answers, baseVersion, skipRest = false) =>
        request<Work>(`/api/works/${id}/answers`, { method: 'POST', body: JSON.stringify({ answers, baseVersion, skipRest }) }),
      confirm: (id, baseVersion) => request<Work>(`/api/works/${id}/spec/confirm`, { method: 'POST', body: JSON.stringify({ baseVersion }) }),
      setAiNote: (id, on) => request<Work>(`/api/works/${id}/ai-note`, { method: 'POST', body: JSON.stringify({ on }) }),
      uploadSource(id, role, file) {
        const form = new FormData()
        form.append('role', role)
        form.append('file', file)
        return request<Work>(`/api/works/${id}/sources`, { method: 'POST', body: form })
      },
      pasteSource: (id, role, name, text) => request<Work>(`/api/works/${id}/sources/text`, { method: 'POST', body: JSON.stringify({ role, name, text }) }),
      removeSource: (id, sourceId) => request<Work>(`/api/works/${id}/sources/${sourceId}`, { method: 'DELETE' }),
      savePlan: (id, plan, baseVersion) => request<Work>(`/api/works/${id}/plan`, { method: 'POST', body: JSON.stringify({ plan, baseVersion }) }),
      approvePlan: (id, baseVersion, acknowledge = []) => request<Work>(`/api/works/${id}/plan/approve`, { method: 'POST', body: JSON.stringify({ baseVersion, acknowledge }) }),
      takeCandidate: (id, accept) => request<Work>(`/api/works/${id}/plan/candidate`, { method: 'POST', body: JSON.stringify({ accept }) }),
      saveResults: (id, results, baseVersion) => request<Work>(`/api/works/${id}/results`, { method: 'POST', body: JSON.stringify({ results, baseVersion }) }),
      approveResults: (id, baseVersion, acknowledge = []) => request<Work>(`/api/works/${id}/results/approve`, { method: 'POST', body: JSON.stringify({ baseVersion, acknowledge }) }),
      saveBudget: (id, budget, baseVersion) => request<Work>(`/api/works/${id}/budget`, { method: 'POST', body: JSON.stringify({ budget, baseVersion }) }),
      quoteStep: (id, step, note) => request<WorkStepQuote>(`/api/works/${id}/steps`, { method: 'POST', body: JSON.stringify({ step, note }) }),
      submitStep: async (id, jobId, quoteId) => {
        await request<Job>(`/api/works/${id}/steps/${jobId}/submit`, { method: 'POST', body: JSON.stringify({ quoteId }) })
      },
      requestChanges: (id, instruction, sections) => request<Work>(`/api/works/${id}/requests`, { method: 'POST', body: JSON.stringify({ instruction, sections }) }),
      requestChangesWithDocument: (id, instruction, sections, file) =>
        request<Work>(`/api/works/${id}/requests/with-document`, { method: 'POST', body: withDocument({ instruction, sections: sections.join(',') }, file) }),
      read: (id) => request<Work>(`/api/works/${id}/read`, { method: 'POST' }),
      start: (id) => request<Work>(`/api/works/${id}/start`, { method: 'POST' }),
      applyFigures: (id) => request<Work>(`/api/works/${id}/figures`, { method: 'POST' }),
      removeRequest: (id, requestId) => request<Work>(`/api/works/${id}/requests/${requestId}`, { method: 'DELETE' }),
      setVersion: (id, version) => request<Work>(`/api/works/${id}/version`, { method: 'POST', body: JSON.stringify({ version }) }),
      document: (id, version) => request<WorkDocumentView>(`/api/works/${id}/document${query({ version })}`),
      download: (id, fileName, version) => saveFile(`/api/works/${id}/export${query({ version })}`, fileName),
      downloadPdf: (id, fileName, version) => saveFile(`/api/works/${id}/export.pdf${query({ version })}`, fileName),
      remove: (id) => request<void>(`/api/works/${id}`, { method: 'DELETE' }),
    },

    datalab: {
      list: () => request<DataProject[]>('/api/datalab'),
      get: (id) =>
        request<DataProject>(`/api/datalab/${encodeURIComponent(id)}`).catch((err: unknown) => {
          if (err instanceof DataError && err.status === 404) return null
          throw err
        }),
      create: (title, purpose, kind = 'QUANT') => request<DataProject>('/api/datalab', { method: 'POST', body: JSON.stringify({ title, purpose, kind }) }),
      addDocument(id, file, choice) {
        const form = new FormData()
        form.append('file', file)
        form.append('label', choice.label)
        form.append('consent', String(choice.consent))
        form.append('country', choice.country)
        form.append('replace', JSON.stringify(choice.replace))
        return request<DataProject>(`/api/datalab/${id}/documents`, { method: 'POST', body: form })
      },
      addText: (id, text, choice) => request<DataProject>(`/api/datalab/${id}/documents/text`, { method: 'POST', body: JSON.stringify({ ...choice, text }) }),
      removeDocument: (id, documentId) => request<DataProject>(`/api/datalab/${id}/documents/${documentId}`, { method: 'DELETE' }),
      startThemes: async (id) => {
        await request<Job>(`/api/datalab/${id}/themes`, { method: 'POST' })
      },
      downloadCodebook: (id, fileName, version) => saveFile(`/api/datalab/${id}/report/codebook${query({ version: version ? String(version) : null })}`, fileName),
      update: (id, change) => request<DataProject>(`/api/datalab/${id}/details`, { method: 'POST', body: JSON.stringify(change) }),
      upload(id, file, choice) {
        const form = new FormData()
        form.append('file', file)
        form.append('country', choice.country)
        form.append('consent', String(choice.consent))
        form.append('removed', JSON.stringify(choice.removed))
        return request<DataProject>(`/api/datalab/${id}/dataset`, { method: 'POST', body: form })
      },
      countries: () => request<{ iso3: string; name: string; available: boolean }[]>('/api/datalab/countries'),
      identifierRules: () => request<IdentifierRules>('/api/datalab/identifier-rules'),
      chooseSheet: (id, name) => request<DataProject>(`/api/datalab/${id}/sheet`, { method: 'POST', body: JSON.stringify({ name }) }),
      preview: (id, offset = 0) => request<DataPreview>(`/api/datalab/${id}/preview${query({ offset: offset ? String(offset) : null })}`),
      editVariable: (id, name, edit) =>
        request<DataProject>(`/api/datalab/${id}/variables/${encodeURIComponent(name)}`, { method: 'POST', body: JSON.stringify(edit) }),
      decide: (id, stepId, accept) => request<DataProject>(`/api/datalab/${id}/cleaning/${stepId}`, { method: 'POST', body: JSON.stringify({ accept }) }),
      undo: (id) => request<DataProject>(`/api/datalab/${id}/undo`, { method: 'POST' }),
      analyse: (id, spec) => request<DataProject>(`/api/datalab/${id}/analyses`, { method: 'POST', body: JSON.stringify(spec) }),
      places: () => request<Places>('/api/datalab/places'),
      setObjective: (id, analysisId, objective) =>
        request<DataProject>(`/api/datalab/${id}/analyses/${analysisId}/objective`, { method: 'POST', body: JSON.stringify({ objective }) }),
      analysis: (id, analysisId) => request<AnalysisResult>(`/api/datalab/${id}/analyses/${analysisId}`),
      chartUrl: async (id, analysisId) => URL.createObjectURL(await blob(`/api/datalab/${id}/analyses/${analysisId}/chart.png`)),
      removeAnalysis: (id, analysisId) => request<DataProject>(`/api/datalab/${id}/analyses/${analysisId}`, { method: 'DELETE' }),
      startReport: async (id, analyses = [], missingOk = []) => {
        await request<Job>(`/api/datalab/${id}/report`, { method: 'POST', body: JSON.stringify({ analyses, missingOk }) })
      },
      report: (id, version) => request<ReportDocument>(`/api/datalab/${id}/report${query({ version: version ? String(version) : null })}`),
      downloadReport: (id, fileName, version) => saveFile(`/api/datalab/${id}/report/export${query({ version: version ? String(version) : null })}`, fileName),
      downloadReportPdf: (id, fileName, version) => saveFile(`/api/datalab/${id}/report/export.pdf${query({ version: version ? String(version) : null })}`, fileName),
      downloadWorkbook: (id, fileName) => saveFile(`/api/datalab/${id}/workbook`, fileName),
      makeCleaned: (id) => request<DataProject>(`/api/datalab/${id}/cleaned`, { method: 'POST' }),
      downloadCleaned: (id, fileName) => saveFile(`/api/datalab/${id}/cleaned`, fileName),
      remove: (id) => request<void>(`/api/datalab/${id}`, { method: 'DELETE' }),
      forProposal: (proposalId) => request<DataProject>(`/api/datalab/for-proposal/${proposalId}`, { method: 'POST' }),
    },

    admin: {
      summary: () => request<AdminSummary>('/api/admin/summary'),
      reliability: (days) => request<import('../features/admin/reliability-page').Reliability>(`/api/admin/reliability?days=${days}`),
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
