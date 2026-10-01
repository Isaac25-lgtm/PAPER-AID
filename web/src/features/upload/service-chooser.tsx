import { clsx } from 'clsx'
import { ArrowRight, BookCheck, Check, FilePen, FileSearch, HandCoins, Lightbulb, NotebookPen, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'
import { Badge } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { AVAILABILITY_BADGE, INVITE_ONLY_REASON, NOT_CONFIGURED_REASON, SECTIONS, type SectionInfo } from '../../lib/services'
import { START_CHOICES } from '../../lib/start'
import type { ServiceId, ServiceSelection } from '../../lib/types'
import { useTitle } from '../../lib/use-title'

/** A kind of job the student can start: what it does, and the selection it starts from. */
export interface JobType {
  id: string
  service: ServiceId // whose availability applies
  name: string
  short: string
  youGet: string[]
  accepts: string
  selection?: Partial<ServiceSelection> // undefined: a link elsewhere (a proposal project)
  to?: string
  icon: typeof FilePen
  soon?: string[]
}

const section = (info: SectionInfo, selection: Partial<ServiceSelection>): JobType => ({
  id: info.id,
  service: info.service,
  name: info.name,
  short: info.short,
  youGet: info.youGet,
  accepts: info.accepts,
  selection,
  icon: info.icon,
  soon: info.soon,
})
const [PAPER_CHECK_INFO, PROPOSALS_INFO, FORMAT_INFO] = SECTIONS
const PAPER_CHECK = section(PAPER_CHECK_INFO, { writing: 'AI_CHECK' })
const ACADEMIC_FORMAT = section(FORMAT_INFO, { writing: 'NONE', formatting: 'FORMAT' })

// Three sections (owner decision 2026-09-29). Redraft, source check, university templates and LaTeX
// are steps and choices inside them, no longer jobs of their own.
export const JOB_GROUPS: { title: string; types: JobType[] }[] = [
  { title: PAPER_CHECK_INFO.name, types: [PAPER_CHECK] },
  {
    title: PROPOSALS_INFO.name,
    types: [
      {
        id: 'PROPOSAL_REVIEW',
        service: 'PROPOSAL',
        name: 'Review my proposal',
        short: 'Check a research proposal you have written, the way an examiner would.',
        youGet: ['Missing sections, alignment of objectives and questions, tense and references', 'What a supervisor is likely to raise', 'A readiness checklist and a Word report'],
        accepts: 'DOCX or text-based PDF (your proposal is not changed)',
        selection: { writing: 'NONE', proposal: 'REVIEW' },
        icon: FileSearch,
      },
      {
        id: 'PROPOSAL_CONCEPT',
        service: 'PROPOSAL',
        name: 'Write a concept note',
        short: 'Your research concept paper first: researched evidence, a plan you approve, then the concept paper. Continue into the full proposal when ready.',
        youGet: ['A plan you edit and approve first', 'A concept paper written from confirmed sources', 'Continue into the full proposal on the same project'],
        accepts: 'Your topic and study details (no upload needed)',
        to: '/app/start/concept-paper',
        icon: Lightbulb,
      },
      {
        id: 'PROPOSAL_PROJECT',
        service: 'PROPOSAL',
        name: 'Write a research proposal',
        short: 'From your topic: researched evidence, a plan you approve, then Chapters One to Three.',
        youGet: ['A plan you edit and approve first', 'Chapters written from confirmed sources', 'A properly formatted Word file'],
        accepts: 'Your topic and study details (no upload needed)',
        to: '/app/start/proposal',
        icon: FilePen,
      },
    ],
  },
  {
    title: 'Coursework',
    types: [
      {
        id: 'COURSEWORK',
        service: 'COURSEWORK',
        name: 'Write coursework',
        short: 'Essays, reports, case studies, literature reviews, short research papers and reflective work, planned from your brief.',
        youGet: ['Every part of the question found and planned', 'A draft from confirmed sources in your referencing style', 'Each rubric criterion checked (not a grade)'],
        accepts: 'Your question, plus the brief and rubric if you have them',
        to: '/app/start/coursework',
        icon: NotebookPen,
      },
    ],
  },
  {
    title: 'Funding',
    types: [
      {
        id: 'CONCEPT_NOTE',
        service: 'CONCEPT_NOTE',
        name: 'Write a concept note',
        short: 'A funding or project concept note, checked against the call.',
        youGet: ['What the call requires, read and quoted', 'A plan you approve first', 'Every limit and form box checked'],
        accepts: 'Your idea, plus the call or template if you have one',
        to: '/app/start/concept-note',
        icon: Lightbulb,
      },
      {
        id: 'FUNDING_PROPOSAL',
        service: 'FUNDING_PROPOSAL',
        name: 'Write a funding proposal',
        short: 'A full proposal built on your Results Model, with the budget and tables checked by code.',
        youGet: ['Eligibility and requirements read from the call', 'Logframe, workplan and M&E table from your Results Model', 'Every budget sum checked'],
        accepts: 'The call and template, plus your project details',
        to: '/app/start/funding',
        icon: HandCoins,
      },
    ],
  },
  { title: FORMAT_INFO.name, types: [ACADEMIC_FORMAT] },
]

// Links from before the sections (bookmarks, emails, the old menu) open the section they now belong
// to, at the step they asked for: the id is kept, so the starting step and choices are the same.
const EARLIER: Record<string, JobType> = {
  AI_CHECK: PAPER_CHECK,
  REFINE: PAPER_CHECK,
  REDRAFT: PAPER_CHECK,
  SOURCE_CHECK: PAPER_CHECK,
  FORMAT: ACADEMIC_FORMAT,
  TEMPLATE_FORMAT: ACADEMIC_FORMAT,
  LATEX: ACADEMIC_FORMAT,
}

export function jobType(id: string | null): JobType | null {
  if (!id) return null
  const current = JOB_GROUPS.flatMap((g) => g.types).find((t) => t.id === id && t.selection)
  return current ?? (EARLIER[id] ? { ...EARLIER[id], id } : null)
}

/** The New page (owner decision 2026-10-01): every service, grouped, the flagship first. Each card is
 *  one link with a labelled action; a service only invited testers can use says so; one that is only
 *  "coming soon" is not shown at all. */
export function ServiceChooser() {
  useTitle('New')
  const { config } = useData()
  const review = JOB_GROUPS.flatMap((g) => g.types).find((t) => t.id === 'PROPOSAL_REVIEW')
  const cards: { group: string; id: string; name: string; short: string; benefits: string[]; action: string; icon: typeof FilePen; to: string; service: ServiceId; soon?: string[] }[] = [
    ...START_CHOICES.map((c) => ({ ...c, group: c.group as string })),
    ...(review ? [{ group: 'Research proposals', id: review.id, name: 'Review my proposal', short: 'Your own proposal checked the way an examiner would.',
      benefits: ['What a supervisor is likely to raise', 'A readiness checklist and a Word report'], action: 'Review my proposal', icon: FileSearch,
      to: `/app/new?service=${review.id}`, service: review.service }] : []),
  ].filter((c) => config.availability[c.service] && config.availability[c.service] !== 'soon')
  const groups = ['Coursework', 'Research proposals', 'Funding', 'Your own paper'].map((g) => ({ title: g, cards: cards.filter((c) => c.group === g) })).filter((g) => g.cards.length)
  return (
    <>
      <div className="mb-8 rounded-3xl bg-gradient-to-br from-brand-50 via-white to-brand-50/60 px-6 py-7 ring-1 ring-brand-100 sm:px-8">
        <p className="text-xs font-semibold tracking-[0.18em] text-brand-700 uppercase">Get started</p>
        <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-fg sm:text-3xl">
          What would you like <span className="text-brand-700">PaperAid</span> to do?
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-fg-muted sm:text-base">Choose what you need. Answer a few questions, then PaperAid gets to work and opens the finished document.</p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-fg-muted">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-line"><ShieldCheck className="size-3.5 text-brand-700" aria-hidden /> Your work stays private</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-line"><BookCheck className="size-3.5 text-brand-700" aria-hidden /> Only sources PaperAid confirmed</span>
        </div>
      </div>
      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.title} aria-labelledby={`group-${group.title}`}>
            <h2 id={`group-${group.title}`} className="mb-3 text-lg font-semibold text-fg">
              {group.title}
            </h2>
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {group.cards.map((card) => {
                const availability = config.availability[card.service]
                const reason = availability === 'invite_only' ? INVITE_ONLY_REASON : availability === 'not_configured' ? NOT_CONFIGURED_REASON : null
                const body = (
                  <div className={clsx('flex h-full flex-col rounded-2xl border bg-white p-5 shadow-card transition', reason ? 'border-line opacity-75' : 'border-line-strong/70 group-hover:-translate-y-0.5 group-hover:border-brand-500 group-hover:shadow-raised')}>
                    <div className="flex items-start gap-3">
                      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700 ring-1 ring-brand-100">
                        <card.icon className="size-5" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-2 text-base font-semibold text-fg">
                          {card.name} {availability === 'invite_only' && <Badge>{AVAILABILITY_BADGE.invite_only}</Badge>}
                        </p>
                        <p className="mt-1 text-sm leading-relaxed text-fg-muted">{reason ?? card.short}</p>
                      </div>
                    </div>
                    <ul className="mt-4 space-y-1.5">
                      {card.benefits.slice(0, 2).map((item) => (
                        <li key={item} className="flex gap-2 text-sm text-fg-muted">
                          <Check className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {item}
                        </li>
                      ))}
                    </ul>
                    {'soon' in card && card.soon?.map((item) => (
                      <p key={item} className="mt-2 flex items-center gap-2 text-xs text-fg-subtle">
                        {item} <Badge>Coming soon</Badge>
                      </p>
                    ))}
                    {!reason && (
                      <span className="mt-auto pt-5">
                        <span className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand-700 px-4 text-sm font-semibold text-white group-hover:bg-brand-800">
                          {card.action} <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
                        </span>
                      </span>
                    )}
                  </div>
                )
                return (
                  <li key={card.id}>
                    {reason ? (
                      <div aria-disabled className="h-full cursor-not-allowed">
                        {body}
                      </div>
                    ) : (
                      <Link to={card.to} className="group block h-full rounded-2xl focus:outline-none focus-visible:ring-3 focus-visible:ring-brand-300">
                        {body}
                      </Link>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  )
}
