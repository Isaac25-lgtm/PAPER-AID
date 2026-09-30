// Domain contracts shared by every screen. When the backend exists these are
// generated from its Pydantic models; until then this file mirrors that plan.
import type { Level, ProposalReview } from './proposal-types'

export type ServiceId = 'AI_CHECK' | 'REFINE' | 'FORMAT' | 'TEMPLATE_FORMAT' | 'REDRAFT' | 'LATEX' | 'SOURCE_CHECK' | 'PROPOSAL' | 'CONCEPT_NOTE' | 'COURSEWORK' | 'FUNDING_PROPOSAL'
/** soon = not built yet; not_configured = the server's AI keys are not set; invite_only = testing is
 *  limited to invited testers and this visitor isn't one (or isn't signed in). */
export type Availability = 'available' | 'soon' | 'not_configured' | 'invite_only'

export type JobStatus =
  | 'DRAFT'
  | 'QUOTED'
  | 'AWAITING_PAYMENT'
  | 'QUEUED'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type Stage = 'EXTRACTING' | 'ANALYSING' | 'RESEARCHING' | 'PLANNING' | 'CONVERTING' | 'REFINING' | 'REDRAFTING' | 'DRAFTING' | 'FORMATTING' | 'AUDITING' | 'EXPORTING'
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

export type WritingStyle = 'PRESERVE_VOICE' | 'STANDARD_ACADEMIC' | 'CONCISE_ACADEMIC' | 'TECHNICAL'

export interface ServiceSelection {
  writing: 'NONE' | 'AI_CHECK' | 'REFINE' | 'REDRAFT'
  intensity: Intensity
  style: WritingStyle
  sourceCheck: boolean
  formatting: 'NONE' | 'FORMAT' | 'TEMPLATE_FORMAT'
  preset: string
  latex: boolean
  /** Academic or research work: adds the academic, evidence and methodology review. */
  academic?: boolean
  /** "Fix selected": refine exactly these passages. */
  onlyBlocks?: string[]
  /** The student's own layout choices over the preset (unset: the preset's). */
  custom?: CustomLayout | null
  /** An institution logo at the top of the first page. */
  logo?: 'NONE' | 'CENTER' | 'LEFT'
  /** A proposal project's step, or REVIEW: an uploaded proposal checked against the rulebook. */
  proposal?: 'NONE' | 'PLAN' | 'CHAPTER_1' | 'CHAPTER_2' | 'CHAPTER_3' | 'REVIEW'
  level?: Level
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
  /** Share of the paper the plan will rewrite (0-1). */
  intervention?: number | null
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
  opId?: string | null
  actor?: string | null
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
  | 'REPETITION'
  | 'STYLE_SHIFT'
  | 'OVERCLAIMING'
  | 'EXCESSIVE_HEDGING'
  | 'VAGUE_WORDING'
  | 'UNSUPPORTED_INTERPRETATION'
  | 'TENSE_INCONSISTENCY'
  | 'WEAK_FLOW'
  | 'CLAIM_WITHOUT_EVIDENCE'
  | 'CAUSAL_OVERSTATEMENT'
  | 'CONFLICTING_NUMBERS'
  | 'CURRENT_STATISTIC'
  | 'OBJECTIVE_METHOD_MISMATCH'
  | 'DESIGN_MISMATCH'
  | 'SAMPLE_INCONSISTENCY'
  | 'MISSING_VALIDITY'
  | 'HEADING_AS_TEXT'
  | 'HEADING_LEVEL_SKIP'
  | 'CAPTION_NUMBERING'

export type FindingCategory = 'AI_LIKE' | 'ACADEMIC' | 'EVIDENCE' | 'METHOD' | 'FORMATTING'

export interface Finding {
  id: string
  blockId: string
  section: string
  reason: ReasonCode
  severity: 'minor' | 'moderate' | 'major'
  excerpt: string
  explanation: string
  suggestion: string
  category: FindingCategory
  /** PaperAid may fix it without the student's judgement. */
  safe: boolean
}

export interface AnalysisResult {
  /** These score fields are absent from student responses while AI scoring is disabled. */
  band?: Band
  confidence?: Confidence
  /** Estimated AI-likeness as a percentage, present only when scoring is enabled and available. */
  percent?: number | null
  coverageComplete?: boolean | null
  disagreementBlocks?: string[]
  analysedWords: number
  excludedWords: number
  findings: Finding[]
  algorithmVersion: string
  method?: string
  /** Academic, evidence, methodology and formatting findings (not part of the band). */
  review: Finding[]
}

export interface CustomLayout {
  font?: string | null
  sizePt?: number | null
  lineSpacing?: number | null
  marginCm?: number | null
  alignment?: 'left' | 'justify' | null
}

export interface ImageMeta {
  name: string
  format: 'PNG' | 'JPEG'
  sizeBytes: number
  widthPx: number
  heightPx: number
}

export interface ReferenceCheck {
  entry: string
  status: 'VERIFIED' | 'PROBABLE' | 'MISMATCH' | 'NOT_VERIFIED'
  doi: string
  matchedTitle: string
  matchedYear: string
  retracted: boolean
  note: string
}

export interface ReferenceVerification {
  items: ReferenceCheck[]
  checked: number
  total: number
  retrievedOn: string
}

export interface ProtectedSummary {
  numbers: number
  citations: number
  quotations: number
  links: number
  wordItems: number
}

/** The paper as PaperAid read it, for the review workspace. */
export interface JobDocument {
  blocks: { id: string; kind: string; level: number | null; section: string; text: string }[]
  /** Deep Redraft: which paragraphs each redrafted group covers. */
  groups: Record<string, string[]>
  /** Recovered after-refinement score for older results, when their saved analysis is available. */
  percentAfter?: number | null
  /** Every change in full (the job record may shorten long passages). */
  changes: ChangedBlock[]
  /** The percentage, recalculated for results recorded before it was kept on the job. */
  percent?: number | null
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
  mode: 'REFINE' | 'REDRAFT' // REDRAFT: each change is a group of paragraphs
  trimmed: boolean // long passages are shortened here; the change report has every word
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
  source: FileMeta | null // null only on a draft before its upload
  guideline: FileMeta | null
  logo?: ImageMeta | null
  quote: Quote | null // null on a draft that has not been priced
  estimate: EstimateView | null
  billing: Billing
  outcome: 'FULL' | 'PARTIAL' | null
  warnings: string[]
  analysis: AnalysisResult | null
  analysisAfter: AnalysisResult | null
  protected?: ProtectedSummary | null
  references?: ReferenceVerification | null
  dismissed?: string[]
  rejectedChanges?: string[]
  sourceJob?: string | null
  /** A continued draft: what each chosen passage should change (the student's request, or findings). */
  fixNotes?: Record<string, string[]>
  paperChecks: PaperChecks | null
  research: ResearchResult | null
  latex: LatexResult | null
  refinement: RefinementResult | null
  formatting: FormattingResult | null
  proposalReview?: ProposalReview | null
  projectId?: string | null
  outputs: OutputFile[]
  failure: JobFailure | null
  createdAt: string
  queuedAt: string | null
  completedAt: string | null
  expiresAt: string
}

export type SupportLevel = 'SUPPORTED' | 'PARTLY_SUPPORTED' | 'CONTRADICTED' | 'NOT_FOUND' | 'UNCERTAIN' | 'UNCONFIRMED'

export interface Source {
  url: string
  title: string
  publisher: string
  published: string
  access: 'FULL_TEXT' | 'ABSTRACT' | 'SNIPPET'
  passage: string
  scope: string
  supports: Exclude<SupportLevel, 'UNCERTAIN' | 'UNCONFIRMED'>
  verified: boolean // PaperAid found the quoted passage on the page itself, or in the article's abstract
  readable: boolean // PaperAid could open the page or abstract (false: blocked, paywalled, unreachable)
}

export interface CheckedClaim {
  id: string
  blockId: string
  section: string
  claim: string
  cited: boolean
  support: SupportLevel
  note: string
  sources: Source[]
}

export interface LatexResult {
  compiled: boolean
  equations: number
  equationsConverted: number
  figures: number
  warnings: string[]
}

export interface ResearchResult {
  claims: CheckedClaim[]
  checked: number
  candidates: number
  retrievedOn: string
  method: string
}

/** A citation/reference or consistency result; `certainty` says how sure PaperAid is. */
export interface PaperCheck {
  kind: 'CITED_NOT_LISTED' | 'LISTED_NOT_CITED' | 'UNREADABLE_CITATION' | 'UNREADABLE_REFERENCE' | 'NO_REFERENCE_LIST' | 'SPELLING_MIXED'
  certainty: 'CONFIRMED' | 'POSSIBLE' | 'UNDETERMINED'
  item: string
  detail: string
}

export interface PaperChecks {
  citationsFound: number
  referencesFound: number
  style: 'AUTHOR_DATE' | 'NUMERIC' | 'UNKNOWN'
  items: PaperCheck[]
  method: string
}

export interface Page<T> {
  items: T[]
  nextCursor: string | null
}

export interface ModelCall {
  stage: Stage
  phase: 'estimate' | 'job'
  provider: string
  model: string
  promptVersion: string
  inputTokens: number
  outputTokens: number
  cachedTokens: number
  cacheWriteTokens: number
  searchCalls: number
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
  /** The AI-likeness percentage and band are shown only when on (off since the 2026-09-30 pilot). */
  aiScore?: boolean
  minTopUpUgx: number
  ugxPerUsd: number
  ugxPerToken: number
  /** Fixed prices by page band (tokens per service; each covers `bandPages` pages, each further band adds `bandStep`). */
  pricing: {
    mode: 'fixed' | 'cost'
    bandPages: number
    bandStep: number
    tokens: Record<string, number>
    formatUgxPer300Words: number
    formatMinUgx: number
    latexUgxPer300Words: number
    latexMinUgx: number
  }
  retentionDays: number
  presets: { id: string; label: string; available: boolean }[]
}
