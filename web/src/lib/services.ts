import type { LucideIcon } from 'lucide-react'
import { Braces, FileCheck2, GraduationCap, PenLine, Search, Shuffle } from 'lucide-react'
import type { Availability, JobStatus, ReasonCode, ServiceId, Stage } from './types'

interface ServiceInfo {
  name: string
  short: string
  icon: LucideIcon
  accepts: string
  youGet: string[]
  untouched: string[]
}

export const AVAILABILITY_BADGE: Record<Exclude<Availability, 'available'>, string> = { soon: 'Coming soon', not_configured: 'Not set up' }
export const NOT_CONFIGURED_REASON = "Unavailable: this server's AI service has not been set up yet."

// Display copy only. Availability and prices come from the server's public config.
export const SERVICES: Record<ServiceId, ServiceInfo> = {
  AI_CHECK: {
    name: 'AI Check',
    short: 'See which passages read as generic or formulaic, and why.',
    icon: Search,
    accepts: 'DOCX or text-based PDF',
    youGet: ['Estimated AI-likeness band with a confidence level', 'Passage-by-passage findings with reasons', 'A downloadable report'],
    untouched: ['Your document — AI Check never edits it'],
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
    youGet: ['Redrafted Word file', 'Section-by-section change summary', 'Independent accuracy audit'],
    untouched: ['Your sources, data and findings'],
  },
  LATEX: {
    name: 'LaTeX conversion',
    short: 'Convert your paper into a clean, compilable LaTeX project.',
    icon: Braces,
    accepts: 'DOCX',
    youGet: ['.tex project with figures', 'Compiled PDF when possible'],
    untouched: ['Your wording and references'],
  },
}

export const SERVICE_ORDER: ServiceId[] = ['AI_CHECK', 'REFINE', 'FORMAT', 'TEMPLATE_FORMAT', 'REDRAFT', 'LATEX']

export const STAGE_LABELS: Record<Stage, string> = {
  EXTRACTING: 'Reading your document',
  ANALYSING: 'Reviewing writing patterns',
  PLANNING: 'Agreeing the refinement plan',
  REFINING: 'Refining flagged passages',
  REDRAFTING: 'Redrafting sections',
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
}
