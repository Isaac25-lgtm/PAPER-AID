import { createContext, useContext } from 'react'
import type {
  AdminJob,
  AdminSummary,
  FileMeta,
  FileRole,
  Job,
  JobStatus,
  Page,
  PublicConfig,
  Quote,
  ServiceId,
  ServiceSelection,
} from './types'

export interface JobQuery {
  cursor?: string | null
  status?: JobStatus | 'ALL'
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
  watchJob(jobId: string, onChange: (job: Job | null) => void): () => void
  createDraft(): Promise<string>
  uploadFile(draftId: string, role: FileRole, file: File, onProgress: (pct: number) => void): Promise<FileMeta>
  /** Detaches the formatting guide on the server and clears any quote that priced it. */
  removeGuideline(draftId: string): Promise<void>
  requestQuote(draftId: string, selection: ServiceSelection): Promise<Quote>
  submitJob(draftId: string, quoteId: string): Promise<string>
  cancelJob(jobId: string): Promise<void>
  deleteJob(jobId: string): Promise<void>
  download(jobId: string, outputId: string, fileName: string): Promise<void>
  deleteAccount(): Promise<void>
  admin: {
    summary(): Promise<AdminSummary>
    listJobs(query: JobQuery): Promise<Page<AdminJob>>
    getJob(jobId: string): Promise<AdminJob | null>
    retryJob(jobId: string): Promise<void>
    cancelJob(jobId: string): Promise<void>
    setProcessing(enabled: boolean): Promise<void>
  }
}

export const DataContext = createContext<DataSource | null>(null)

export function useData() {
  const source = useContext(DataContext)
  if (!source) throw new Error('useData must be used inside <DataContext>')
  return source
}
