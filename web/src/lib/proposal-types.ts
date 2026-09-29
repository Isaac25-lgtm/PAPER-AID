// Proposal project contracts, mirroring backend/app/proposals/models.py (camelCase on the wire).
import type { Job, Quote, QuoteLine } from './types'

export type Level = 'BACHELORS' | 'PGD' | 'MASTERS' | 'PHD'
export type StudyType = 'QUANTITATIVE' | 'QUALITATIVE' | 'MIXED' | 'SECONDARY' | 'NON_EMPIRICAL'
export type CitationStyle = 'APA6' | 'APA7'
export type SampleMethod = 'YAMANE' | 'COCHRAN' | 'KREJCIE_MORGAN' | 'CENSUS' | 'SATURATION' | 'AUTHOR_STATED' | 'NOT_APPLICABLE'
export type StepId = 'PLAN' | 'CHAPTER_1' | 'CHAPTER_2' | 'CHAPTER_3' | 'CONCEPT' | 'REVISE_1' | 'REVISE_2' | 'REVISE_3' | 'REVISE_4' | 'PROFILE'
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
  /** The student's own figures: the only accepted source of a population size or stated sample. */
  populationSize: number | null
  populationSource: string
  expectedParticipants: number | null
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

/** The gap the study fills: what confirmed evidence shows, what it leaves open, what the study adds. */
export interface ResearchGap {
  known: string
  missing: string
  contribution: string
  /** Ids of the confirmed evidence "known" rests on. */
  evidence: string[]
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
  researchGap: ResearchGap
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
  /** 1-3: the proposal's chapters; 4: the concept paper, a separate document. */
  number: 1 | 2 | 3 | 4
  current: number
  approved: boolean
  versions: ChapterVersion[]
  needsReview: string[]
}

export type FeedbackStatus = 'OPEN' | 'APPLIED' | 'DONE_BY_STUDENT' | 'DECLINED'

/** One supervisor comment: where it applies, and what was done about it. */
export interface FeedbackComment {
  id: string
  round: number
  text: string
  anchor: string
  chapter: 1 | 2 | 3 | null
  sections: string[]
  status: FeedbackStatus
  appliedIn: number | null
  response: string
  /** STUDENT: the student's own request for changes (not a supervisor comment). */
  by?: 'SUPERVISOR' | 'STUDENT'
}

export interface WrittenSection {
  chapter: 1 | 2 | 3
  key: string
  number: string
  heading: string
}

export interface Comparison {
  number: number
  older: number
  newer: number
  changed: number
  sections: { number: string; heading: string; status: 'SAME' | 'CHANGED' | 'ADDED' | 'REMOVED'; pieces: { op: 'same' | 'added' | 'removed'; text: string }[] }[]
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
  autoChapterOne: boolean
  feedback: FeedbackComment[]
  /** The current chapters' sections, where comments can be placed. */
  written: WrittenSection[]
  /** What stands between the proposal and a complete download. */
  blockers: string[]
  /** The institution the proposal is written for, what its guide left open, and the guide's file. */
  institution: string
  institutionNotes: string[]
  guideName: string | null
  /** The current profile was read from the current guide. */
  guideRead: boolean
  /** The institution's profile can no longer be read: the proposal can go back to the standard structure. */
  profileMissing?: boolean
  /** A one-off message returned by an action (for example why Chapter One did not start). */
  notice: string | null
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
  sections: { key: string; number: string; heading: string; paragraphs: string[]; table: string[][] | null; tableCaption: string; needsReview: boolean }[]
  readiness: ReadinessItem[]
  warnings: string[]
  words: number
  references: string[]
  /** Chapter One's conceptual framework, drawn from the plan's variables. */
  framework: { label: string; items: string[] }[]
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
  /** Shown with the plan: Chapter One, which starts automatically when the plan is approved. */
  then: QuoteLine[]
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
