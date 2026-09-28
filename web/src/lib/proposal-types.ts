// Proposal project contracts, mirroring backend/app/proposals/models.py (camelCase on the wire).
import type { Job, Quote } from './types'

export type Level = 'BACHELORS' | 'PGD' | 'MASTERS' | 'PHD'
export type StudyType = 'QUANTITATIVE' | 'QUALITATIVE' | 'MIXED' | 'SECONDARY' | 'NON_EMPIRICAL'
export type CitationStyle = 'APA6' | 'APA7'
export type SampleMethod = 'YAMANE' | 'COCHRAN' | 'KREJCIE_MORGAN' | 'CENSUS' | 'SATURATION' | 'AUTHOR_STATED' | 'NOT_APPLICABLE'
export type StepId = 'PLAN' | 'CHAPTER_1' | 'CHAPTER_2' | 'CHAPTER_3'
export type ReadinessStatus = 'PASS' | 'NEEDS_REVIEW' | 'MISSING' | 'NOT_APPLICABLE' | 'BLOCKED'

export interface ProposalInputs {
  topic: string
  level: Level
  programme: string
  faculty: string
  studyArea: string
  population: string
  studyType: StudyType | null
  notes: string
}

export interface TitlePage {
  studentName: string
  regNumber: string
  supervisor: string
  submissionDate: string
}

export interface SampleSize {
  method: SampleMethod
  population: number | null
  populationSource: string
  margin: number
  confidence: 90 | 95 | 99
  proportion: number
  stated: number | null
  rationale: string
}

export interface AlignmentRow {
  objective: number
  data: string
  collection: string
  analysis: string
}

export interface ProposalPlan {
  title: string
  problem: string
  purpose: string
  specificObjectives: string[]
  questionsKind: 'QUESTIONS' | 'HYPOTHESES' | 'PROPOSITIONS'
  researchQuestions: string[]
  studyType: StudyType
  design: string
  studyArea: string
  population: string
  sampling: string
  sampleSize: SampleSize
  inclusion: string
  variables: { independent: string[]; dependent: string[]; intervening: string[] }
  alignment: AlignmentRow[]
  theory: string
  scope: string
  timelineMonths: number
  gaps: string[]
  questionsForStudent: string[]
}

export interface ChapterVersion {
  version: number
  jobId: string
  createdAt: string
  words: number
  planVersion: number
  passed: number
  total: number
  note: string
}

export interface ChapterState {
  number: 1 | 2 | 3
  current: number
  approved: boolean
  versions: ChapterVersion[]
  needsReview: string[]
}

export interface Project {
  id: string
  kind: 'PROPOSAL'
  rulebook: string
  citation: CitationStyle
  inputs: ProposalInputs
  titlePage: TitlePage
  plan: ProposalPlan | null
  planStatus: 'NONE' | 'DRAFT' | 'APPROVED'
  planVersion: number
  planProblems: string[]
  candidatePlan: ProposalPlan | null
  chapters: ChapterState[]
  evidenceCount: number
  activeJob: string | null
  jobs: string[]
  createdAt: string
  updatedAt: string
  expiresAt: string
}

export interface ReadinessItem {
  id: string
  question: string
  status: ReadinessStatus
  basis: 'CODE' | 'AI' | 'AUTHOR'
  note: string
  where: string
  chapter: number
}

export interface ChapterView {
  number: number
  title: string
  version: number
  planVersion: number
  sections: { number: string; heading: string; paragraphs: string[]; table: string[][] | null; tableCaption: string; needsReview: boolean }[]
  readiness: ReadinessItem[]
  warnings: string[]
  words: number
  references: string[]
}

export interface EvidenceItem {
  id: string
  chapter: number
  need: string
  statement: string
  passage: string
  scope: string
  access: 'FULL_TEXT' | 'ABSTRACT' | 'SNIPPET'
  verified: boolean
  support: 'SUPPORTED' | 'PARTLY_SUPPORTED' | 'CONTRADICTED' | 'NOT_FOUND'
  source: { url: string; title: string; authors: string[]; organisation: string; year: string; container: string; doi: string; metadata: 'CROSSREF' | 'OPENALEX' | 'PAGE' }
  retrievedOn: string
}

export interface StepQuote {
  job: Job
  quote: Quote
}

export interface Rulebook {
  id: string
  institution: string
  source: string
  levels: Record<Level, { label: string; pages: [number, number] }>
  citationProfiles: Record<CitationStyle, string>
  defaultCitation: CitationStyle
}

export interface ProposalReview {
  rulebook: string
  level: Level
  words: number
  items: ReadinessItem[]
  findings: { where: string; kind: 'ALIGNMENT' | 'EVIDENCE' | 'METHOD' | 'STRUCTURE' | 'TENSE' | 'WRITING'; severity: 'major' | 'moderate' | 'minor'; issue: string; suggestion: string }[]
  method: string
}
