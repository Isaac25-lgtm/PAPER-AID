// Domain contracts shared by every screen. When the backend exists these are
// generated from its Pydantic models; until then this file mirrors that plan.

export type ServiceId = 'AI_CHECK' | 'REFINE' | 'FORMAT' | 'TEMPLATE_FORMAT' | 'REDRAFT' | 'LATEX'
/** soon = not built yet; not_configured = built, but the server's AI keys are not set. */
export type Availability = 'available' | 'soon' | 'not_configured'

export type JobStatus =
  | 'DRAFT'
  | 'QUOTED'
  | 'AWAITING_PAYMENT'
  | 'QUEUED'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type Stage = 'EXTRACTING' | 'ANALYSING' | 'PLANNING' | 'REFINING' | 'REDRAFTING' | 'FORMATTING' | 'AUDITING' | 'EXPORTING'
export type PaymentStatus = 'NOT_REQUIRED' | 'PENDING' | 'PAID' | 'FAILED' | 'REFUNDED'
export type FileRole = 'source' | 'guideline'
export type Intensity = 'LIGHT' | 'STANDARD'
export type Band = 'LOW' | 'MODERATE' | 'HIGH'
export type Confidence = 'LOW' | 'MEDIUM' | 'HIGH'

export interface FileMeta {
  name: string
  format: 'DOCX' | 'PDF'
  sizeBytes: number
  wordCount: number
  pageEstimate: number
  headingCount: number
}

export interface ServiceSelection {
  writing: 'NONE' | 'AI_CHECK' | 'REFINE' | 'REDRAFT'
  intensity: Intensity
  formatting: 'NONE' | 'FORMAT' | 'TEMPLATE_FORMAT'
  preset: string
  latex: boolean
}

export interface QuoteLine {
  label: string
  amount: number
}

/** `amount` is the most the job can cost, everything included; `paid` is the part already charged (the AI estimate). */
export interface Quote {
  id: string
  currency: 'UGX'
  lines: QuoteLine[]
  amount: number
  paid: number
  pricingVersion: string
  expiresAt: string
}

/** The paid AI scan that sizes a refinement before it is priced. */
export interface EstimateView {
  status: 'RUNNING' | 'READY' | 'FAILED'
  feeCap: number
  fee: number
  message: string | null
}

export interface QuoteResponse {
  quote: Quote | null
  estimate: EstimateView | null
  /** Refinement: the most the estimate can cost, shown before the student starts it. */
  estimateFeeCap: number | null
}

export interface Billing {
  state: 'NONE' | 'HELD' | 'SETTLED' | 'RELEASED'
  feePaid: number
  held: number
  charged: number
  refunded: number
}

export interface LedgerEntry {
  id: string
  at: string
  kind: 'TOP_UP' | 'HOLD' | 'CHARGE' | 'RELEASE' | 'REFUND'
  amount: number
  jobId: string | null
  note: string
  availableAfter: number
  heldAfter: number
}

export interface Wallet {
  currency: 'UGX'
  available: number
  held: number
  entries: LedgerEntry[]
  ugxPerUsd: number
  /** Local mode: credits exist only for testing and are not money. */
  testCredits: boolean
}

export interface WalletSummary {
  email: string
  available: number
  held: number
  updatedAt: string
}

export type ReasonCode =
  | 'GENERIC_PHRASING'
  | 'UNIFORM_STRUCTURE'
  | 'LOW_SPECIFICITY'
  | 'FORMULAIC_TRANSITIONS'
  | 'OVER_HEDGING'
  | 'UNSUPPORTED_SUMMARY'

export interface Finding {
  id: string
  blockId: string
  section: string
  reason: ReasonCode
  severity: 'minor' | 'moderate' | 'major'
  excerpt: string
  explanation: string
  suggestion: string
}

export interface AnalysisResult {
  band: Band
  confidence: Confidence
  analysedWords: number
  excludedWords: number
  findings: Finding[]
  algorithmVersion: string
  method?: string
}

export interface ChangedBlock {
  blockId: string
  section: string
  before: string
  after: string
  kept: boolean
  note?: string
  /** The instruction the two models agreed for this passage. */
  reason?: string
}

export interface RefinementResult {
  targetedBlocks: number
  refinedBlocks: number
  keptOriginal: number
  untouchedBlocks: number
  changes: ChangedBlock[]
  method?: string
}

export interface FormattingResult {
  preset: string
  rules: { label: string; value: string }[]
  bodyTextUnchanged: boolean
  warnings: string[]
  /** For an uploaded guide: the sentence each rule came from. */
  evidence?: { rule: string; quote: string }[]
  method?: string
}

export interface OutputFile {
  id: string
  label: string
  name: string
  sizeBytes: number
}

export interface JobFailure {
  code: string
  userMessage: string
  retryable: boolean
}

export interface Job {
  id: string
  status: JobStatus
  stage: Stage | null
  paymentStatus: PaymentStatus
  selection: ServiceSelection
  services: ServiceId[]
  pipeline: Stage[]
  source: FileMeta
  guideline: FileMeta | null
  quote: Quote
  estimate: EstimateView | null
  billing: Billing
  outcome: 'FULL' | 'PARTIAL' | null
  warnings: string[]
  analysis: AnalysisResult | null
  analysisAfter: AnalysisResult | null
  refinement: RefinementResult | null
  formatting: FormattingResult | null
  outputs: OutputFile[]
  failure: JobFailure | null
  createdAt: string
  queuedAt: string | null
  completedAt: string | null
  expiresAt: string
}

export interface Page<T> {
  items: T[]
  nextCursor: string | null
}

export interface ModelCall {
  stage: Stage
  provider: string
  model: string
  promptVersion: string
  inputTokens: number
  outputTokens: number
  cachedTokens: number
  latencyMs: number
  costUsd: number
}

export interface AdminJob {
  job: Job
  ownerEmail: string
  costUsd: number
  durationSec: number | null
  modelCalls: ModelCall[]
  events: { at: string; label: string }[]
  adminActions: { at: string; actor: string; action: string }[]
  failureDetail?: string | null
}

export interface AdminSummary {
  jobs24h: number
  active: number
  queued: number
  completionRate: number
  failures24h: number
  spend24hUsd: number
  processingEnabled: boolean
}

export interface PublicConfig {
  paymentsEnabled: boolean
  availability: Record<ServiceId, Availability>
  /** Off = testing mode: nothing needs a balance and nothing is charged; prices are still shown. */
  creditsEnabled: boolean
  minTopUpUgx: number
  ugxPerUsd: number
  retentionDays: number
  presets: { id: string; label: string; available: boolean }[]
}
