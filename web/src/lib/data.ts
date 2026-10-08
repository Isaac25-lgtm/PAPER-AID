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
  LedgerEntry,
  Page,
  PublicConfig,
  QuoteResponse,
  ServiceId,
  ServiceSelection,
  Wallet,
  WalletSummary,
} from './types'
import type { AnalysisResult, AnalysisSpec, DataPreview, DataProject, IdentifierRules, Places, ReportDocument, TranscriptChoice, UploadChoice, VariableKind } from './datalab-types'
import type { ChapterView, CitationStyle, Comparison, EvidenceItem, FeedbackStatus, FrameworkStyle, Project, ProposalInputs, ProposalPlan, Rulebook, SampleSize, StepId, StepQuote, TitlePage, Variables } from './proposal-types'
import type { Budget, ResultsModel, SourceRole, Work, WorkCitation, WorkDocumentView, WorkInputs, WorkKind, WorkPlan, WorkStep, WorkStepQuote } from './work-types'

export interface Notifications {
  available: { email: boolean; sms: boolean }
  notifyEmail: boolean
  notifySms: boolean
  phone: string
}

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
    readonly code?: string,
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
  /** The complete history, newest first; `before` is the previous page's `next`. */
  walletHistory(before: string | null): Promise<{ entries: LedgerEntry[]; next: string | null }>
  submitJob(draftId: string, quoteId: string): Promise<string>
  cancelJob(jobId: string): Promise<void>
  deleteJob(jobId: string): Promise<void>
  download(jobId: string, outputId: string, fileName: string): Promise<void>
  deleteAccount(): Promise<void>
  /** The person accepted these terms (at sign-up, or when asked again). */
  acceptTerms(version: string): Promise<void>
  /** "Your work is ready" messages: which channels exist and the account's choices. */
  notifications(): Promise<Notifications>
  setNotifications(choice: Partial<Omit<Notifications, 'available'>>): Promise<Notifications>
  /** The review workspace. */
  workspace: {
    document(jobId: string): Promise<JobDocument>
    setFinding(jobId: string, findingId: string, dismissed: boolean): Promise<Job>
    setChange(jobId: string, changeId: string, accepted: boolean): Promise<Job>
    rebuild(jobId: string): Promise<Job>
    /** A new refinement draft of the same paper for the chosen findings (or every safe one). */
    fix(jobId: string, findingIds: string[], safeOnly: boolean): Promise<Job>
    /** The next job on the same paper: from the original or the finished one, optionally with the
     *  student's own instruction for chosen passages (or the whole paper). */
    continueFrom(jobId: string, origin: 'original' | 'result', instruction?: string, blocks?: string[]): Promise<Job>
  }
  /** Proposal projects: the plan, chapters and evidence live on the server; every paid step is a job. */
  projects: {
    rulebook(): Promise<Rulebook>
    list(): Promise<Project[]>
    get(id: string): Promise<Project | null>
    create(inputs: ProposalInputs, titlePage: TitlePage, citation: CitationStyle, goal?: 'FULL' | 'CONCEPT'): Promise<Project>
    /** A concept-note project becomes a full proposal (nothing starts by itself). */
    continueToFull(id: string): Promise<Project>
    updateDetails(id: string, inputs: ProposalInputs, titlePage: TitlePage, citation: CitationStyle): Promise<Project>
    /** Where the study takes place and who it studies, as PaperAid proposed them or as the student corrects them. */
    confirmSetting(id: string, studyArea: string, population: string, baseVersion: number): Promise<Project>
    /** Keep the guide's version of a point where it departs from the standard guide, or take the standard one. */
    answerGuide(id: string, departureId: string, answer: 'KEEP' | 'STANDARD'): Promise<Project>
    /** `baseVersion` is the plan version the edit started from; a stale edit is refused (409). */
    savePlan(id: string, plan: ProposalPlan, baseVersion: number): Promise<Project>
    approvePlan(id: string, baseVersion: number, acknowledge?: string[]): Promise<Project>
    takeCandidate(id: string, accept: boolean): Promise<Project>
    sampleSize(id: string, sample: SampleSize): Promise<{ size: number | null; steps: string; missing: string }>
    quoteStep(id: string, step: StepId, note: string, comments?: string[]): Promise<StepQuote>
    submitStep(id: string, jobId: string, quoteId: string): Promise<void>
    chapter(id: string, number: number, version?: number): Promise<ChapterView>
    setChapter(id: string, number: number, version: number, approved: boolean): Promise<Project>
    evidence(id: string): Promise<EvidenceItem[]>
    download(id: string, final: boolean, fileName: string): Promise<void>
    /** The same proposal as a PDF, for reading and sharing (Word stays the file to submit). */
    downloadPdf(id: string, final: boolean, fileName: string): Promise<void>
    /** The complete proposal as a LaTeX project (.zip), converted by code. */
    downloadLatex(id: string, final: boolean, fileName: string): Promise<void>
    remove(id: string): Promise<void>
    compare(id: string, number: number, older: number, newer: number): Promise<Comparison>
    /** Supervisor comments, pasted or from a marked-up Word file or PDF. */
    addFeedback(id: string, text: string): Promise<Project>
    addFeedbackFile(id: string, file: File): Promise<Project>
    editFeedback(id: string, commentId: string, edit: { chapter: number | null; sections: string[]; status: FeedbackStatus; response: string }): Promise<Project>
    deleteFeedback(id: string, commentId: string): Promise<Project>
    downloadResponse(id: string): Promise<void>
    downloadConcept(id: string, fileName: string): Promise<void>
    /** The student's own request for changes to a chapter (4: the concept paper). */
    requestChanges(id: string, chapter: number, instruction: string, sections: string[]): Promise<Project>
    /** The same, with a document (Word or PDF) whose text the writer gets for context. */
    requestChangesWithDocument(id: string, chapter: number, instruction: string, sections: string[], file: File): Promise<Project>
    /** One Start (owner decision 2026-10-01): plan, then the first chapter, by itself. */
    start(id: string, acceptSampling?: boolean): Promise<Project>
    /** The conceptual framework figure, as an image the page can show. */
    framework(id: string): Promise<Blob>
    /** The student's edit of the framework: its style (only redraws it) or its variables. */
    editFramework(id: string, baseVersion: number, change: { style?: FrameworkStyle; variables?: Variables }): Promise<Project>
    /** The institution's research guide, read into a profile by the PROFILE step. */
    uploadGuide(id: string, file: File): Promise<Project>
    useDefaultRulebook(id: string): Promise<Project>
  }
  /** Works: concept notes, coursework and funding proposals. Every edit names its base version. */
  works: {
    list(): Promise<Work[]>
    get(id: string): Promise<Work | null>
    create(kind: WorkKind, variant: string, mode: string, inputs: WorkInputs, citation: WorkCitation): Promise<Work>
    updateDetails(id: string, inputs: WorkInputs, change: { mode?: string; variant?: string; citation?: WorkCitation }, baseVersion: number): Promise<Work>
    answer(id: string, answers: Record<string, string>, baseVersion: number, skipRest?: boolean): Promise<Work>
    confirm(id: string, baseVersion: number): Promise<Work>
    setAiNote(id: string, on: boolean): Promise<Work>
    uploadSource(id: string, role: SourceRole, file: File): Promise<Work>
    pasteSource(id: string, role: SourceRole, name: string, text: string): Promise<Work>
    removeSource(id: string, sourceId: string): Promise<Work>
    savePlan(id: string, plan: WorkPlan, baseVersion: number): Promise<Work>
    approvePlan(id: string, baseVersion: number, acknowledge?: string[]): Promise<Work>
    takeCandidate(id: string, accept: boolean): Promise<Work>
    saveResults(id: string, results: ResultsModel, baseVersion: number): Promise<Work>
    approveResults(id: string, baseVersion: number, acknowledge?: string[]): Promise<Work>
    saveBudget(id: string, budget: Budget, baseVersion: number): Promise<Work>
    quoteStep(id: string, step: WorkStep, note: string): Promise<WorkStepQuote>
    submitStep(id: string, jobId: string, quoteId: string): Promise<void>
    requestChanges(id: string, instruction: string, sections: string[]): Promise<Work>
    /** The same, with a document (Word or PDF) whose text the writer gets for context. */
    requestChangesWithDocument(id: string, instruction: string, sections: string[], file: File): Promise<Work>
    removeRequest(id: string, requestId: string): Promise<Work>
    /** One Start (owner decision 2026-10-01): read the documents just added (no charge of its own). */
    read(id: string): Promise<Work>
    /** One Start: confirm, check credits, plan; the draft follows by itself. */
    start(id: string): Promise<Work>
    /** The student's saved figures go into the current document (code only, no charge). */
    applyFigures(id: string): Promise<Work>
    setVersion(id: string, version: number): Promise<Work>
    document(id: string, version?: number): Promise<WorkDocumentView>
    download(id: string, fileName: string, version?: number): Promise<void>
    downloadPdf(id: string, fileName: string, version?: number): Promise<void>
    remove(id: string): Promise<void>
  }
  /** Data Lab (owner decision 2026-10-03): datasets analysed by code, written up as an analysis report. */
  datalab: {
    list(): Promise<DataProject[]>
    get(id: string): Promise<DataProject | null>
    create(title: string, purpose: string, kind?: 'QUANT' | 'QUAL'): Promise<DataProject>
    /** Qualitative: a transcript file, or pasted text, kept after the names listed are replaced. */
    addDocument(id: string, file: File, choice: TranscriptChoice): Promise<DataProject>
    addText(id: string, text: string, choice: TranscriptChoice): Promise<DataProject>
    removeDocument(id: string, documentId: string): Promise<DataProject>
    startThemes(id: string): Promise<void>
    downloadCodebook(id: string, fileName: string, version?: number): Promise<void>
    update(id: string, change: { title?: string; purpose?: string; alpha?: number; threshold?: number }): Promise<DataProject>
    upload(id: string, file: File, choice: UploadChoice): Promise<DataProject>
    countries(): Promise<{ iso3: string; name: string; available: boolean }[]>
    identifierRules(): Promise<IdentifierRules>
    chooseSheet(id: string, name: string): Promise<DataProject>
    preview(id: string, offset?: number): Promise<DataPreview>
    editVariable(id: string, name: string, edit: { label?: string; kind?: VariableKind; excluded?: boolean; survey?: 'DESIGN' | 'NOT_DESIGN' }): Promise<DataProject>
    decide(id: string, stepId: string, accept: boolean): Promise<DataProject>
    undo(id: string): Promise<DataProject>
    /** Checked at once, run by the worker: follow the project's `op` to the result. */
    analyse(id: string, spec: AnalysisSpec): Promise<DataProject>
    setObjective(id: string, analysisId: string, objective: number | null): Promise<DataProject>
    /** Uganda's regions and sub-regions, for the map step. */
    places(): Promise<Places>
    analysis(id: string, analysisId: string): Promise<AnalysisResult>
    chartUrl(id: string, analysisId: string): Promise<string>
    removeAnalysis(id: string, analysisId: string): Promise<DataProject>
    /** `missingOk`: Chapter Four objectives the researcher confirmed have no analysis. */
    startReport(id: string, analyses?: string[], missingOk?: number[]): Promise<void>
    report(id: string, version?: number): Promise<ReportDocument>
    downloadReport(id: string, fileName: string, version?: number): Promise<void>
    downloadReportPdf(id: string, fileName: string, version?: number): Promise<void>
    downloadWorkbook(id: string, fileName: string): Promise<void>
    /** The researcher's own cleaned data (individual records): made by the worker, then downloaded. */
    makeCleaned(id: string): Promise<DataProject>
    downloadCleaned(id: string, fileName: string): Promise<void>
    remove(id: string): Promise<void>
    /** Chapter Four: the Data Lab project for a research proposal's data (created on first use). */
    forProposal(proposalId: string): Promise<DataProject>
  }
  admin: {
    summary(): Promise<AdminSummary>
    /** Reliability by service (owner roadmap 2026-10-03): numbers and codes only. */
    reliability(days: number): Promise<import('../features/admin/reliability-page').Reliability>
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
