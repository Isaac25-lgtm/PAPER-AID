/** Data Lab (owner decision 2026-10-03): the server's records, as the browser shows them. Every
 *  number comes from the server; the browser never calculates. */

export type VariableKind = 'NUMERIC' | 'CATEGORICAL' | 'BINARY' | 'DATE' | 'TEXT' | 'IDENTIFIER'
export type VariableFlag = 'PERSONAL' | 'RECORD_ID' | 'SURVEY_DESIGN' | 'LOCATION' | 'FEW_VALUES' | 'LEADING_ZEROS' | 'MIXED' | 'LONG_NUMBER' | 'DECIMAL_COMMA'

/** The rules for columns that may identify people or places: the same file the server reads. */
export interface IdentifierRules {
  headers: Record<string, string>
  /** Names a header rule never applies to (a district's or a school's name is not personal). */
  except?: Record<string, string>
  values: Record<string, string>
  share: number
  labels: Record<string, string>
}

/** What goes with an upload: the data's country, the researcher's confirmations, the columns removed on their device. */
export interface UploadChoice {
  country: string
  consent: boolean
  removed: string[]
}

export interface DataVariable {
  name: string
  label: string
  kind: VariableKind
  stored: 'number' | 'text' | 'date'
  valid: number
  missing: number
  distinct: number
  levels: { value: string; count: number }[]
  summary: Record<string, number>
  flags: VariableFlag[]
  excluded: boolean
  note: string
}

export interface CleaningStep {
  id: string
  kind: 'TRIM' | 'MERGE_LEVELS' | 'SET_MISSING' | 'OUT_OF_RANGE' | 'DUPLICATES' | 'DECIMAL_COMMA'
  column: string
  description: string
  question: string
  affected: number
  automatic: boolean
  status: 'PROPOSED' | 'APPLIED' | 'DECLINED'
  version: number | null
  decidedAt: string | null
}

export interface DatasetVersion {
  version: number
  rows: number
  columns: number
  createdAt: string
  note: string
}

export interface AnalysisRef {
  id: string
  kind: AnalysisKind
  title: string
  status: AnalysisStatus
  version: number
  objective: number | null
  createdAt: string
  /** The data or a setting it used changed after it ran: run it again before reporting it. */
  stale: boolean
}

/** Data work the worker is doing for the project (reading a file, a change, an analysis, the cleaned data). */
export interface DataOp {
  kind: 'LOAD' | 'SHEET' | 'DECIDE' | 'UNDO' | 'ANALYSE' | 'CLEANED'
  status: 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED'
  error: string
  code: string
  result: string
}

export interface ReportVersion {
  version: number
  jobId: string
  analyses: string[]
  kind: 'REPORT' | 'CHAPTER_FOUR'
  createdAt: string
}

export interface DataProject {
  id: string
  title: string
  purpose: string
  createdAt: string
  updatedAt: string
  expiresAt: string
  source: { name: string; bytes: number; sheet: string | null; sheets: string[]; removed: string[] } | null
  rows: number
  columns: number
  version: number
  versions: DatasetVersion[]
  variables: DataVariable[]
  pending: CleaningStep[]
  applied: CleaningStep[]
  survey: 'NONE' | 'ASK' | 'DESIGN'
  surveyColumns: string[]
  analyses: AnalysisRef[]
  reports: ReportVersion[]
  reportCurrent: number
  activeJob: string | null
  reportFailure: string
  alpha: number
  threshold: number
  availability: string
  reportPriced: boolean
  proposalId: string
  objectives: string[]
  op: DataOp | null
  cleanedReady: boolean
  /** Columns that may identify people or places, included by the researcher (a recorded decision). */
  released: { name: string; at: string; by: string }[]
}

export type AnalysisKind = 'DESCRIBE' | 'CROSSTAB' | 'COMPARE_TWO' | 'CORRELATE' | 'MAP'
export type AnalysisStatus = 'VALID' | 'VALID_WITH_WARNINGS' | 'NOT_ESTIMABLE'
export type AnalysisMethod = '' | 'MEANS' | 'DISTRIBUTIONS' | 'PEARSON' | 'SPEARMAN' | 'COUNT' | 'MEAN' | 'RATE'

/** A condition on one variable: its categories, or a range of numbers or dates (YYYY-MM-DD). */
export interface DataFilter {
  variable: string
  op: 'IN' | 'NOT_IN' | 'BETWEEN'
  values: string[]
  low: string
  high: string
}

export type MapLevel = 'DISTRICT' | 'SUBCOUNTY' | 'SUBREGION' | 'REGION'

export interface Places {
  regions: string[]
  subregions: { name: string; districts: string[] }[]
}

export interface AnalysisSpec {
  kind: AnalysisKind
  variables: string[]
  method: AnalysisMethod
  groups: string[]
  question: string
  objective?: number | null
  filters?: DataFilter[]
  region?: '' | 'Central' | 'Eastern' | 'Northern' | 'Western'
  subregion?: string
  aliases?: Record<string, string>
  level?: MapLevel
  subcounty?: string
  dataForm?: 'RECORDS' | 'TOTALS'
  total?: string
  denominator?: string
}

export interface ResultCell {
  text: string
  value: number | null
  count: boolean
  suppressed: boolean
}

export interface ResultTable {
  title: string
  columns: string[]
  rows: ResultCell[][]
  notes: string[]
}

export interface Estimate {
  name: string
  value: number
  low: number | null
  high: number | null
  level: number
  note: string
}

export interface CalculationRecord {
  question: string
  method: string
  why: string
  datasetVersion: number
  cleaning: string[]
  rowsUsed: number
  rowsAvailable: number
  leftOut: string[]
  coding: string[]
  missing: string
  alpha: number
  assumptions: string[]
  software: string[]
  calculatedAt: string
}

export interface AnalysisResult {
  id: string
  spec: AnalysisSpec
  status: AnalysisStatus
  title: string
  tables: ResultTable[]
  statistics: Record<string, number>
  estimates: Estimate[]
  sentences: string[]
  warnings: string[]
  record: CalculationRecord
  chart: string
  matches: Record<string, string>
  unmatched: string[]
  createdAt: string
}

export interface ReportSection {
  key: string
  heading: string
  paragraphs: string[]
  bullets: string[]
  tables: ResultTable[]
  chart: string
  notes: string[]
  level: number
}

export interface ReportDocument {
  title: string
  subtitle: string
  createdAt: string
  sections: ReportSection[]
  appendices: ReportSection[]
  words: number
}

export interface DataPreview {
  columns: string[]
  rows: string[][]
  total: number
  offset: number
}
