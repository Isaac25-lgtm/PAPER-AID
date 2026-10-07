import type { LucideIcon } from 'lucide-react'
import { BookCheck, Braces, ChartColumn, FileCheck2, GraduationCap, HandCoins, Lightbulb, NotebookPen, PenLine, Search, Shuffle } from 'lucide-react'
import type { Availability, FindingCategory, JobStatus, ReasonCode, ServiceId, Stage, WritingStyle } from './types'

interface ServiceInfo {
  name: string
  short: string
  icon: LucideIcon
  accepts: string
  youGet: string[]
  untouched: string[]
}

export const AVAILABILITY_BADGE: Record<Exclude<Availability, 'available'>, string> = { soon: 'Coming soon', not_configured: 'Not set up', invite_only: 'Invite only' }
export const NOT_CONFIGURED_REASON = "Unavailable: this server's AI service has not been set up yet."
export const INVITE_ONLY_REASON = 'Open to invited testers while PaperAid is in testing. Academic formatting is open to everyone.'

/** The three sections students choose from (owner decision 2026-09-29). Services are steps inside
 *  them: Redraft, Ask for changes, Source check and Finish live in Paper Check; university templates
 *  and LaTeX are finishing choices. `service` is whose availability the section follows. */
export interface SectionInfo {
  id: 'PAPER_CHECK' | 'PROPOSALS' | 'ACADEMIC_FORMAT' | 'COURSEWORK' | 'FUNDING' | 'DATALAB'
  service: ServiceId
  name: string
  short: string
  icon: LucideIcon
  accepts: string
  youGet: string[]
  untouched: string[]
  to: string
  /** Shown as "coming soon", never as something the student can choose (owner decision 2026-09-30). */
  soon?: string[]
}

export const SECTIONS: SectionInfo[] = [
  {
    id: 'PAPER_CHECK',
    // The writing check is hidden until a validated detector is integrated (owner decision 2026-10-07): the
    // section opens on the redraft, which the check's own switch (AI_CHECK_ENABLED) never closes.
    service: 'REFINE',
    name: 'Paper Check',
    short: 'Redraft your paper in your own voice, ask for changes, check its sources and finish it, all on one screen.',
    icon: Search,
    accepts: 'DOCX',
    youGet: [
      'A redraft (light, standard or deep) in your own voice: keep or undo every change',
      'Changes in your own words or your supervisor\'s',
      'Your sources checked, and your paper finished in APA, Harvard, your institution\'s layout or LaTeX',
    ],
    untouched: ['Citations, quotations, numbers and URLs', 'Your argument and findings', 'Anything you choose to keep in your own words'],
    to: '/app/new?service=PAPER_CHECK',
    soon: ['Writing check', 'AI detection'],
  },
  {
    id: 'PROPOSALS',
    service: 'PROPOSAL',
    name: 'Academic research',
    short: 'Your research from concept paper and proposal to results: Chapters One to Three from researched sources, then Chapter Four from your data. Or a review of a proposal you wrote.',
    icon: GraduationCap,
    accepts: 'Your topic and study details, your data for the results, or your proposal as DOCX or PDF',
    youGet: ['Chapter One written as soon as you start, from sources PaperAid confirmed', 'Chapters Two and Three, and changes from your supervisor\'s comments or your own', 'Chapter Four, the results, written objective by objective from your analysed data', 'The complete document in Word, PDF or LaTeX'],
    untouched: ['Facts only you can give: population sizes, instruments and approvals are asked for, never invented'],
    to: '/app/projects',
  },
  {
    id: 'ACADEMIC_FORMAT',
    service: 'FORMAT',
    name: 'Academic Formatting',
    short: 'Lay out a finished paper in APA, Harvard or your institution\'s own guide, with a LaTeX version if you want one.',
    icon: FileCheck2,
    accepts: 'DOCX, plus your guide as DOCX or PDF if you use one',
    youGet: ['APA, Harvard and other styles: headings, spacing and page numbers', 'Your institution\'s guide read into exact rules, with its sources (this uses AI and is priced as such)', 'An optional institution logo and LaTeX version'],
    untouched: ['Every word of your text'],
    to: '/app/new?service=ACADEMIC_FORMAT',
  },
]

// Display copy only. Availability and prices come from the server's public config.
export const SERVICES: Record<ServiceId, ServiceInfo> = {
  AI_CHECK: {
    name: 'Writing check',
    short: 'See which passages read as generic or formulaic, and why.',
    icon: Search,
    accepts: 'DOCX or text-based PDF',
    youGet: ['Generic, formulaic or repetitive passages marked in your paper', 'The reason and a suggestion for each', 'A downloadable writing report'],
    untouched: ['Your document — the writing check never edits it'],
  },
  REFINE: {
    name: 'Check + Refine',
    short: 'Sharpen flagged passages in your own voice. Citations, numbers and quotes stay locked.',
    icon: PenLine,
    accepts: 'DOCX',
    youGet: ['Refined Word file', 'A report of every change and why', 'Before and after writing report'],
    untouched: ['Citations, quotations, numbers and URLs', 'Paragraphs that were not flagged', 'Your argument and findings'],
  },
  FORMAT: {
    name: 'Academic formatting',
    short: 'Page layout, headings, spacing and page numbers set to APA or Harvard — wording untouched.',
    icon: FileCheck2,
    accepts: 'DOCX',
    youGet: ['Formatted Word file', 'Summary of the rules applied', 'Automatic check that no wording changed'],
    untouched: ['Every word of your text'],
  },
  TEMPLATE_FORMAT: {
    name: 'University templates',
    short: "Upload your department's guide and we turn it into exact formatting rules.",
    icon: GraduationCap,
    accepts: 'DOCX, plus your guide as DOCX or PDF',
    youGet: ['Formatted Word file', 'The rules we found in your guide, with sources', 'Warnings where the guide is unclear'],
    untouched: ['Every word of your text'],
  },
  REDRAFT: {
    name: 'Deep redraft',
    short: 'Restructure your own draft section by section, with a full change report.',
    icon: Shuffle,
    accepts: 'DOCX',
    youGet: ['Redrafted Word file', 'Every reworked passage shown before and after', 'Every change checked for accuracy'],
    untouched: ['Citations, quotations, numbers and your findings', 'Headings, lists and tables', 'What each section covers'],
  },
  SOURCE_CHECK: {
    name: 'Source check',
    short: 'Your key factual claims checked against current sources.',
    icon: BookCheck,
    accepts: 'With a redraft, or on its own from your results (DOCX)',
    youGet: ['Each claim marked supported, partly supported, contradicted or not found', 'The sources, with the passage quoted and the date read', 'Sources you could cite for uncited claims'],
    untouched: ['Your paper: claims are reported, never changed'],
  },
  PROPOSAL: {
    name: 'Research proposals',
    short: 'A research proposal or concept paper written chapter by chapter from researched sources, or a review of one you have written.',
    icon: GraduationCap,
    accepts: 'Your topic and study details, or your proposal as DOCX or PDF',
    youGet: ['A readiness checklist of what examiners look for', 'Every claim traced to a source PaperAid confirmed', 'A properly formatted Word file'],
    untouched: ['Facts only you can give: population sizes, instruments and approvals are asked for, never invented'],
  },
  CONCEPT_NOTE: {
    name: 'Concept notes',
    short: 'A funding or project concept note, written to the call and checked against everything it asks.',
    icon: Lightbulb,
    accepts: 'Your idea, plus the call or template as DOCX or PDF if you have one',
    youGet: ['What PaperAid found in the call, for you to confirm', 'Written as soon as you start, with every limit checked', 'The concept note in Word, with its compliance report'],
    untouched: ["Facts only you can give: budgets, dates and your organisation's track record are asked for, never invented"],
  },
  COURSEWORK: {
    name: 'Coursework',
    short: 'Essays, reports, case studies, literature reviews, short research papers and reflective work, planned from your brief.',
    icon: NotebookPen,
    accepts: 'Your assignment question, plus the brief and rubric as DOCX or PDF if you have them',
    youGet: ['Every part of the question found and planned', 'A draft written from confirmed sources in your referencing style', "A check of each rubric criterion (PaperAid's assessment, not a grade)"],
    untouched: ['Your own experience in reflective work: asked for, never invented', 'Quotations and figures you give'],
  },
  FUNDING_PROPOSAL: {
    name: 'Funding proposals',
    short: 'A full funding proposal with its logframe, workplan and budget, every table and sum consistent.',
    icon: HandCoins,
    accepts: 'The call and template as DOCX or PDF, plus your project details',
    youGet: ['Eligibility and requirements read from the call', 'Logframe, workplan and M&E table that agree with each other', 'Every budget sum worked out for you'],
    untouched: ['Your figures: budget lines, targets and dates are yours, never invented; any PaperAid cannot know are marked for you to fill in'],
  },
  DATALAB: {
    name: 'Data Lab',
    short: 'Numbers, maps and interviews analysed and written up, every number calculated by code.',
    icon: ChartColumn,
    accepts: 'CSV or Excel (.xlsx) for numbers and maps; text, Word or PDF transcripts for interviews',
    youGet: ['Data checks and cleaning you confirm', 'Analyses with effect sizes and confidence intervals, and maps of Uganda', 'Themes from interviews with quotes checked word for word',
      'A report in Word and PDF, and an Excel workbook'],
    untouched: ['Your original file: every change makes a new version', 'Columns that may identify people: left out by default; names you list replaced in transcripts'],
  },
  LATEX: {
    name: 'LaTeX conversion',
    short: 'Convert your paper into a clean, compilable LaTeX project.',
    icon: Braces,
    accepts: 'DOCX (on its own, or after refining, redrafting or formatting)',
    youGet: ['.tex project with figures', 'Compiled PDF when possible', 'A list of anything to check by hand'],
    untouched: ['Your wording, citations and reference list'],
  },
}

/** What the public pages describe (owner request 2026-10-02: every section, for researchers and
 *  students), in the New page's order. Availability badges come from the server, as for SECTIONS. */
export const PUBLIC_SECTIONS: SectionInfo[] = [
  {
    id: 'COURSEWORK',
    service: 'COURSEWORK',
    name: 'Coursework',
    short: 'Essays, reports, case studies, literature reviews and reflective work, written to your question and brief.',
    icon: NotebookPen,
    accepts: 'Your question, plus the brief and marking rubric as DOCX or PDF if you have them',
    youGet: ['Every part of the question answered', 'Written from confirmed sources in your referencing style', "Each rubric criterion checked (PaperAid's assessment, not a grade)"],
    untouched: ['Your own experience in reflective work: asked for, never invented', 'Quotations and figures you give'],
    to: '/app/start/coursework',
  },
  SECTIONS[1],
  {
    id: 'FUNDING',
    service: 'FUNDING_PROPOSAL',
    name: 'Funding concept notes and proposals',
    short: 'Concept notes and full funding proposals, written to the call and checked against everything it asks.',
    icon: HandCoins,
    accepts: 'The call or funder’s guidelines as DOCX or PDF (or pasted), plus your project idea',
    youGet: ['Eligibility and requirements read from the call', 'Logframe, workplan and M&E table that agree with each other', 'Every budget sum worked out for you'],
    untouched: ['Your figures: budget lines, targets and dates are yours, never invented; any PaperAid cannot know are marked for you to fill in'],
    to: '/app/start/funding',
  },
  {
    id: 'DATALAB',
    service: 'DATALAB',
    name: 'Data Lab',
    short: 'Quantitative, geospatial and qualitative analysis: PaperAid checks your data, runs the analyses you choose and writes up the report, every number calculated by code.',
    icon: ChartColumn,
    accepts: 'A dataset as CSV or Excel (.xlsx), or interview transcripts as text, Word or PDF',
    youGet: ['Quantitative: describe a variable, compare two groups, relate two categories, correlate two numbers, with effect sizes and confidence intervals, filtered by any variable',
      'Geospatial: maps by district, subcounty, sub-region or region of Uganda, as counts or rates, from official boundaries',
      'Qualitative: codes and themes that answer your question, every quote checked word for word against its transcript',
      'A report in Word and PDF (or Chapter Four of your proposal), and an Excel workbook or codebook'],
    untouched: ['Your original file: never changed', 'Columns that may identify people: left out by default, and small counts never shown', 'Names you list: replaced in transcripts before anything is stored'],
    to: '/app/datalab',
  },
  SECTIONS[0],
  SECTIONS[2],
]

export const SERVICE_ORDER: ServiceId[] = ['AI_CHECK', 'REFINE', 'SOURCE_CHECK', 'FORMAT', 'TEMPLATE_FORMAT', 'REDRAFT', 'LATEX']

export const STAGE_LABELS: Record<Stage, string> = {
  EXTRACTING: 'Reading your document',
  ANALYSING: 'Reviewing writing patterns',
  RESEARCHING: 'Checking claims against live sources',
  CONVERTING: 'Converting to LaTeX',
  PLANNING: 'Agreeing the refinement plan',
  REFINING: 'Refining flagged passages',
  REDRAFTING: 'Redrafting sections',
  DRAFTING: 'Writing the chapter',
  FORMATTING: 'Applying formatting',
  AUDITING: 'Checking accuracy',
  EXPORTING: 'Preparing your files',
}

export const STATUS_LABELS: Record<JobStatus, string> = {
  DRAFT: 'Draft',
  QUOTED: 'Quoted',
  AWAITING_PAYMENT: 'Awaiting payment',
  QUEUED: 'Queued',
  PROCESSING: 'Processing',
  COMPLETED: 'Ready',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
}

export const REASON_LABELS: Record<ReasonCode, string> = {
  GENERIC_PHRASING: 'Generic phrasing',
  UNIFORM_STRUCTURE: 'Repetitive structure',
  LOW_SPECIFICITY: 'Vague claim',
  FORMULAIC_TRANSITIONS: 'Formulaic transition',
  OVER_HEDGING: 'Over-hedging',
  UNSUPPORTED_SUMMARY: 'Unsupported summary',
  REPETITION: 'Repeated phrasing',
  STYLE_SHIFT: 'Style shift',
  OVERCLAIMING: 'Overclaiming',
  EXCESSIVE_HEDGING: 'Too much hedging',
  VAGUE_WORDING: 'Vague wording',
  UNSUPPORTED_INTERPRETATION: 'Unsupported interpretation',
  TENSE_INCONSISTENCY: 'Tense',
  WEAK_FLOW: 'Weak flow',
  CLAIM_WITHOUT_EVIDENCE: 'Claim needs a source',
  CAUSAL_OVERSTATEMENT: 'Cause overstated',
  CONFLICTING_NUMBERS: 'Figures disagree',
  CURRENT_STATISTIC: 'Statistic needs a current source',
  OBJECTIVE_METHOD_MISMATCH: 'Objective and method mismatch',
  DESIGN_MISMATCH: 'Design mismatch',
  SAMPLE_INCONSISTENCY: 'Sample inconsistency',
  MISSING_VALIDITY: 'Validity and reliability',
  HEADING_AS_TEXT: 'Heading typed as text',
  HEADING_LEVEL_SKIP: 'Heading level skipped',
  CAPTION_NUMBERING: 'Caption numbering',
}

export const CATEGORY_LABELS: Record<FindingCategory | 'REFERENCES', string> = {
  AI_LIKE: 'Formulaic writing',
  ACADEMIC: 'Academic writing',
  EVIDENCE: 'Evidence and claims',
  REFERENCES: 'References',
  METHOD: 'Methodology',
  FORMATTING: 'Formatting',
}

export const STYLE_OPTIONS: { id: WritingStyle; title: string; body: string }[] = [
  { id: 'PRESERVE_VOICE', title: 'Preserve my voice', body: 'Keeps your own words and sentence habits wherever they work.' },
  { id: 'STANDARD_ACADEMIC', title: 'Standard academic', body: 'Clear, formal academic English.' },
  { id: 'CONCISE_ACADEMIC', title: 'Concise academic', body: 'Formal and tight: cuts filler, never content.' },
  { id: 'TECHNICAL', title: 'Technical/scientific', body: 'Precise terms for science, engineering and health papers.' },
]
