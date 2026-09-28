import { createContext, useContext } from 'react'
import type {
  AdminJob,
  AdminSummary,
  FileMeta,
  FileRole,
  ImageMeta,
  Job,
  JobDocument,
  JobStatus,
  Page,
  PublicConfig,
  QuoteResponse,
  ServiceId,
  ServiceSelection,
  Wallet,
  WalletSummary,
} from './types'
import type { ChapterView, CitationStyle, EvidenceItem, Project, ProposalInputs, ProposalPlan, Rulebook, SampleSize, StepId, StepQuote, TitlePage } from './proposal-types'

export interface JobQuery {
  cursor?: string | null
  status?: JobStatus | 'ALL' // 'DRAFT' lists unfinished drafts (priced or not) that have a paper
  service?: ServiceId | 'ALL'
  search?: string
  limit?: number
}

export class DataError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
  }
}

// The one seam between screens and data. `api-source.ts` implements it against the PaperAid API.
export interface DataSource {
  config: PublicConfig
  listJobs(query: JobQuery): Promise<Page<Job>>
  /** One of the student's jobs, or null when it no longer exists. */
  getJob(jobId: string): Promise<Job | null>
  /** Polls a job. `onBlocked` receives the server's message when the request is refused (signed out,
   *  or App Check could not verify the browser); polling then stops until the page is refreshed. */
  watchJob(jobId: string, onChange: (job: Job | null) => void, onBlocked?: (message: string) => void): () => void
  createDraft(): Promise<string>
  uploadFile(draftId: string, role: FileRole, file: File, onProgress: (pct: number) => void): Promise<FileMeta>
  /** An institution logo (PNG or JPEG) for the title page; replacing it clears the quote. */
  uploadLogo(draftId: string, file: File): Promise<ImageMeta>
  removeLogo(draftId: string): Promise<void>
  /** Detaches the formatting guide on the server and clears any quote that priced it. */
  removeGuideline(draftId: string): Promise<void>
  /** A price, or for refinement the estimate that runs first (watch the draft until it is READY). */
  requestQuote(draftId: string, selection: ServiceSelection, startEstimate?: boolean): Promise<QuoteResponse>
  getWallet(): Promise<Wallet>
  submitJob(draftId: string, quoteId: string): Promise<string>
  cancelJob(jobId: string): Promise<void>
  deleteJob(jobId: string): Promise<void>
  download(jobId: string, outputId: string, fileName: string): Promise<void>
  deleteAccount(): Promise<void>
  /** The review workspace. */
  workspace: {
    document(jobId: string): Promise<JobDocument>
    setFinding(jobId: string, findingId: string, dismissed: boolean): Promise<Job>
    setChange(jobId: string, changeId: string, accepted: boolean): Promise<Job>
    rebuild(jobId: string): Promise<Job>
    /** A new refinement draft of the same paper for the chosen findings (or every safe one). */
    fix(jobId: string, findingIds: string[], safeOnly: boolean): Promise<Job>
  }
  /** Proposal projects: the plan, chapters and evidence live on the server; every paid step is a job. */
  projects: {
    rulebook(): Promise<Rulebook>
    list(): Promise<Project[]>
    get(id: string): Promise<Project | null>
    create(inputs: ProposalInputs, titlePage: TitlePage, citation: CitationStyle): Promise<Project>
    updateDetails(id: string, inputs: ProposalInputs, titlePage: TitlePage, citation: CitationStyle): Promise<Project>
    /** `baseVersion` is the plan version the edit started from; a stale edit is refused (409). */
    savePlan(id: string, plan: ProposalPlan, baseVersion: number): Promise<Project>
    approvePlan(id: string, baseVersion: number): Promise<Project>
    takeCandidate(id: string, accept: boolean): Promise<Project>
    sampleSize(id: string, sample: SampleSize): Promise<{ size: number | null; steps: string; missing: string }>
    quoteStep(id: string, step: StepId, note: string): Promise<StepQuote>
    submitStep(id: string, jobId: string, quoteId: string): Promise<void>
    chapter(id: string, number: number, version?: number): Promise<ChapterView>
    setChapter(id: string, number: number, version: number, approved: boolean): Promise<Project>
    evidence(id: string): Promise<EvidenceItem[]>
    download(id: string, final: boolean, fileName: string): Promise<void>
    remove(id: string): Promise<void>
  }
  admin: {
    summary(): Promise<AdminSummary>
    listJobs(query: JobQuery): Promise<Page<AdminJob>>
    getJob(jobId: string): Promise<AdminJob | null>
    retryJob(jobId: string): Promise<void>
    cancelJob(jobId: string): Promise<void>
    setProcessing(enabled: boolean): Promise<void>
    listWallets(search: string): Promise<WalletSummary[]>
    /** `opId` identifies one intended grant: sending it again adds nothing. */
    grantCredits(email: string, amount: number, note: string, opId: string): Promise<WalletSummary>
  }
}

export const DataContext = createContext<DataSource | null>(null)

export function useData() {
  const source = useContext(DataContext)
  if (!source) throw new Error('useData must be used inside <DataContext>')
  return source
}
