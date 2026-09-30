// Works (concept notes, coursework, funding proposals): mirrors backend/app/works/models.py and the
// views in app/works/service.py. The browser only displays what the server decides.
import type { ReadinessItem } from './proposal-types'
import type { Job, Quote } from './types'

export type WorkKind = 'CONCEPT_NOTE' | 'COURSEWORK' | 'FUNDING_PROPOSAL'
export type Variant =
  | 'FUNDING_CONCEPT'
  | 'PROJECT_CONCEPT'
  | 'ESSAY'
  | 'ACADEMIC_REPORT'
  | 'CASE_STUDY_ANALYTICAL'
  | 'CASE_STUDY_PROBLEM'
  | 'LITERATURE_REVIEW'
  | 'RESEARCH_PAPER_EMPIRICAL'
  | 'RESEARCH_PAPER_NON_EMPIRICAL'
  | 'REFLECTIVE'
  | 'NGO_PROJECT'
  | 'RESEARCH_GRANT'
export type Mode = '' | 'BRIEF' | 'STANDARD' | 'EXTENDED' | 'COMPACT' | 'COMPREHENSIVE'
export type SourceRole = 'CALL' | 'TEMPLATE' | 'ADDENDUM' | 'BRIEF' | 'RUBRIC' | 'READING' | 'GUIDE' | 'OTHER'
export type WorkCitation = 'APA7' | 'APA6' | 'HARVARD'
export type Readiness = 'NOT_READY' | 'READY_WITH_WARNINGS' | 'READY'
export type WorkStep = 'READ' | 'PLAN' | 'DRAFT' | 'REVISE'
export type Status = 'NONE' | 'DRAFT' | 'APPROVED'

export interface WorkInputs {
  title: string
  description: string
  answers: Record<string, string>
  experience: string
}

export interface SourceView {
  id: string
  name: string
  role: SourceRole
  words: number
  uploadedAt: string
}

export interface Requirement {
  id: string
  key: string
  label: string
  value: string
  number: number | null
  unit: string
  hard: boolean
  authority: string
  source: string
  quote: string
  location: string
  verified: boolean
  confirmed: boolean
  highStakes: boolean
  weight: number | null
  inConflict: boolean
}

export interface Question {
  id: string
  label: string
  help: string
  kind: 'TEXT' | 'LONG' | 'NUMBER' | 'CHOICE' | 'BOOL'
  choices: string[]
  gate: 'BLOCK' | 'ASK_ONCE'
  answered: boolean
  fallback: string
}

export interface Limit {
  type: 'WORD' | 'CHARACTER' | 'FIELD' | 'PAGE'
  max: number
  min: number | null
  field: string
  tolerance: number
}

export interface FormField {
  id: string
  label: string
  maxWords: number | null
  maxCharacters: number | null
}

export interface Criterion {
  id: string
  name: string
  weight: number | null
  descriptor: string
}

export interface CoverageItem {
  id: string
  text: string
  directive: string
}

export interface ResolvedSpec {
  version: number
  kind: WorkKind
  variant: Variant
  mode: Mode
  level: string
  targetWords: number
  limits: Limit[]
  fields: FormField[]
  templateHeadings: string[]
  citationStyle: WorkCitation
  aiPolicy: 'UNKNOWN' | 'BANNED' | 'ALLOWED_WITH_DISCLOSURE' | 'ALLOWED'
  sourcePolicy: 'INDEPENDENT' | 'CLOSED' | 'NONE'
  requiredReadings: string[]
  scoring: Criterion[]
  directives: string[]
  coverage: CoverageItem[]
  priorities: string[]
  eligibility: string[]
  ceiling: number | null
  currency: string
  durationMonths: number | null
  deadline: string
  overlays: string[]
  requirements: Requirement[]
  conflicts: { key: string; requirementIds: string[]; note: string; chosen: string | null }[]
  assumptions: string[]
  questions: Question[]
  gate: 'PASS' | 'ASK_ONCE' | 'BLOCK'
  blockers: string[]
  overridden: string[]
  exploratory: boolean
}

export interface PlanSection {
  key: string
  heading: string
  words: number
  minWords: number
  maxWords: number
  required: boolean
  locked: boolean
  brief: string
  criteria: string[]
  coverage: string[]
  fieldId: string
}

export interface WorkPlan {
  title: string
  position: string
  sections: PlanSection[]
  questionsForStudent: string[]
  notes: string[]
}

export interface ResultsModel {
  goal: { id: string; statement: string }
  objectives: { id: string; statement: string }[]
  outcomes: { id: string; statement: string; objectiveId: string; assumptions: string[] }[]
  outputs: { id: string; statement: string; outcomeId: string }[]
  activities: { id: string; statement: string; outputId: string; ownerRole: string; startMonth: number | null; endMonth: number | null; costed: boolean; major: boolean }[]
  indicators: {
    id: string
    resultId: string
    level: 'goal' | 'outcome' | 'output'
    definition: string
    unit: string
    baseline: number | null
    baselineYear: number | null
    baselinePlan: string
    target: number | null
    targetDate: string
    disaggregation: string[]
    meansOfVerification: string
    frequency: string
    responsibleRole: string
  }[]
  risks: { id: string; statement: string; likelihood: 'low' | 'medium' | 'high'; impact: 'low' | 'medium' | 'high'; mitigation: string; ownerRole: string }[]
  assumptions: string[]
}

export interface BudgetLine {
  id: string
  category: string
  description: string
  quantity: number
  unit: string
  unitCost: number
  enteredTotal: number | null
  year: number
  activityIds: string[]
  support: boolean
  role: string
}

export interface Budget {
  currency: string
  lines: BudgetLine[]
  requested: number | null
  costShareProvided: number | null
  indirectAmount: number | null
  exchangeRate: number | null
  exchangeFrom: string
  exchangeDate: string
}

export interface BudgetTotals {
  total: number
  direct: number
  indirect: number
  byCategory: Record<string, number>
  byYear: Record<string, number>
  lines: Record<string, number>
  currency: string
}

export interface DocVersion {
  version: number
  jobId: string
  createdAt: string
  words: number
  status: Readiness
  note: string
}

export interface ChangeRequest {
  id: string
  text: string
  sections: string[]
  status: 'OPEN' | 'APPLIED' | 'DECLINED'
  appliedIn: number | null
}

export interface Work {
  id: string
  kind: WorkKind
  variant: Variant
  mode: Mode
  level: string
  citation: WorkCitation
  inputs: WorkInputs
  sources: SourceView[]
  spec: ResolvedSpec | null
  specVersion: number
  specStatus: 'NONE' | 'DRAFT' | 'CONFIRMED'
  plan: WorkPlan | null
  planStatus: Status
  planVersion: number
  candidatePlan: WorkPlan | null
  results: ResultsModel | null
  resultsStatus: Status
  resultsVersion: number
  budget: Budget | null
  budgetVersion: number
  documents: DocVersion[]
  current: number
  requests: ChangeRequest[]
  aiNote: boolean
  exploratory: boolean
  readiness: ReadinessItem[]
  status: Readiness | null
  checks: ReadinessItem[]
  needsRead: boolean
  budgetTotals: BudgetTotals | null
  notice: string | null
  activeJob: string | null
  jobs: string[]
  createdAt: string
  updatedAt: string
  expiresAt: string
}

export interface WorkStepQuote {
  job: Job
  quote: Quote
  notice: string | null
}

export interface RenderedSection {
  key: string
  heading: string
  paragraphs: string[]
  table: string[][] | null
  tableCaption: string
  fieldLimit: string
  fieldCount: string
}

export interface WorkDocumentView {
  version: number
  title: string
  status: Readiness
  exploratory: boolean
  sections: RenderedSection[]
  references: string[]
  readiness: ReadinessItem[]
  words: number
  aiNote: string
  tables: { caption: string; rows: string[][] }[]
}
