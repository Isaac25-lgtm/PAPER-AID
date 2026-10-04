import type { LucideIcon } from 'lucide-react'
import { ChartColumn, FileCheck2, FilePen, HandCoins, Lightbulb, NotebookPen, Search } from 'lucide-react'
import type { PublicConfig, ServiceId } from './types'

/** What a student can start, in the order PaperAid offers it (owner decision 2026-10-01: coursework,
 *  the flagship, first). Writing services start with one Start (`/app/start/...`); Paper Check and
 *  Academic Formatting keep their own upload pages. Names say what PaperAid does, never how. */
export interface StartChoice {
  id: StartType | 'PAPER_CHECK' | 'ACADEMIC_FORMAT' | 'DATALAB'
  service: ServiceId // whose availability applies
  group: 'Coursework' | 'Research proposals' | 'Funding' | 'Data analysis' | 'Your own paper'
  name: string
  short: string
  benefits: string[]
  action: string
  icon: LucideIcon
  to: string
  /** Shown as "coming soon", never as something the student can choose (owner decision 2026-09-30). */
  soon?: string[]
}

export type StartType = 'coursework' | 'proposal' | 'concept-paper' | 'concept-note' | 'funding'

export const START_CHOICES: StartChoice[] = [
  {
    id: 'coursework', service: 'COURSEWORK', group: 'Coursework', name: 'Coursework', icon: NotebookPen, to: '/app/start/coursework', action: 'Start coursework',
    short: 'Essays, reports, case studies and reflective work, written to your brief.',
    benefits: ['Every part of the question answered', 'Sources in your referencing style'],
  },
  {
    id: 'proposal', service: 'PROPOSAL', group: 'Research proposals', name: 'Research proposal', icon: FilePen, to: '/app/start/proposal', action: 'Write Chapter One',
    short: 'Chapters One to Three, written to your institution’s guide.',
    benefits: ['Chapter One from confirmed sources', 'A conceptual framework figure'],
  },
  {
    id: 'concept-paper', service: 'PROPOSAL', group: 'Research proposals', name: 'Academic concept paper', icon: Lightbulb, to: '/app/start/concept-paper', action: 'Write my concept paper',
    short: 'A short concept paper for your research topic, before the full proposal.',
    benefits: ['From confirmed sources', 'Continue into the full proposal later'],
  },
  {
    id: 'concept-note', service: 'CONCEPT_NOTE', group: 'Funding', name: 'Funding concept note', icon: Lightbulb, to: '/app/start/concept-note', action: 'Write my concept note',
    short: 'A concept note for a call or a funder, checked against what it asks.',
    benefits: ['What the call requires, read for you', 'Every limit and form box checked'],
  },
  {
    id: 'funding', service: 'FUNDING_PROPOSAL', group: 'Funding', name: 'Funding proposal', icon: HandCoins, to: '/app/start/funding', action: 'Write my proposal',
    short: 'A full proposal with logframe, workplan and budget tables.',
    benefits: ['Tables built from your figures', 'Every budget sum worked out for you'],
  },
  {
    id: 'DATALAB', service: 'DATALAB', group: 'Data analysis', name: 'Data Lab', icon: ChartColumn, to: '/app/datalab', action: 'Analyse my data',
    short: 'Your dataset checked, analysed and written up, every number calculated by code.',
    benefits: ['Cleaning you confirm, nothing changed silently', 'An analysis report and an Excel workbook'],
  },
  {
    id: 'PAPER_CHECK', service: 'AI_CHECK', group: 'Your own paper', name: 'Paper Check', icon: Search, to: '/app/new?service=PAPER_CHECK', action: 'Check my paper',
    short: 'Writing feedback on your own paper, then a redraft in your voice if you want one.',
    benefits: ['Generic or repetitive passages marked, with reasons', 'Citations, quotations and numbers kept'],
    soon: ['AI detection'],
  },
  {
    id: 'ACADEMIC_FORMAT', service: 'FORMAT', group: 'Your own paper', name: 'Academic formatting', icon: FileCheck2, to: '/app/new?service=ACADEMIC_FORMAT', action: 'Format my paper',
    short: 'Your finished paper laid out in APA, Harvard or your institution’s guide.',
    benefits: ['Headings, spacing and page numbers', 'Every word of your text kept'],
  },
]

/** The choices this server offers now (never one that is only "coming soon"). */
export function startChoices(config: Pick<PublicConfig, 'availability'>) {
  return START_CHOICES.filter((c) => config.availability[c.service] && config.availability[c.service] !== 'soon')
}
