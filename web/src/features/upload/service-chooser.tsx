import { clsx } from 'clsx'
import { ArrowRight, Check, FilePen, FileSearch } from 'lucide-react'
import { Link } from 'react-router'
import { Badge, PageHeader } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { AVAILABILITY_BADGE, INVITE_ONLY_REASON, NOT_CONFIGURED_REASON, SECTIONS, type SectionInfo } from '../../lib/services'
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
        id: 'PROPOSAL_PROJECT',
        service: 'PROPOSAL',
        name: 'Write a research proposal',
        short: 'From your topic: researched evidence, a plan you approve, then Chapters One to Three.',
        youGet: ['A plan you edit and approve first', 'Chapters written from confirmed sources', 'A properly formatted Word file'],
        accepts: 'Your topic and study details (no upload needed)',
        to: '/app/projects/new',
        icon: FilePen,
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

/** The first step of a new job: choose what PaperAid will do, then upload knowing what happens. */
export function ServiceChooser() {
  useTitle('New job')
  const { config } = useData()
  return (
    <>
      <PageHeader title="What would you like PaperAid to do?" description="Choose the job first. You upload your paper on the next page and see the price before anything starts." />
      <div className="space-y-8">
        {JOB_GROUPS.map((group) => (
          <section key={group.title} aria-labelledby={`group-${group.title}`}>
            <h2 id={`group-${group.title}`} className="mb-3 text-sm font-semibold tracking-wide text-fg-subtle uppercase">
              {group.title}
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {group.types.map((type) => {
                const availability = config.availability[type.service]
                const reason = availability === 'invite_only' ? INVITE_ONLY_REASON : availability === 'not_configured' ? NOT_CONFIGURED_REASON : availability === 'soon' ? 'Coming soon.' : null
                const card = (
                  <div className={clsx('flex h-full flex-col rounded-2xl border bg-white p-5 shadow-card transition-colors', reason ? 'border-line opacity-70' : 'border-line group-hover:border-brand-400')}>
                    <div className="flex items-start gap-3">
                      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
                        <type.icon className="size-5" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-2 font-semibold text-fg">
                          {type.name} {availability !== 'available' && <Badge>{AVAILABILITY_BADGE[availability]}</Badge>}
                        </p>
                        <p className="mt-1 text-sm leading-relaxed text-fg-muted">{reason ?? type.short}</p>
                      </div>
                    </div>
                    <ul className="mt-4 space-y-1.5">
                      {type.youGet.map((item) => (
                        <li key={item} className="flex gap-2 text-xs text-fg-muted">
                          <Check className="mt-0.5 size-3.5 shrink-0 text-brand-600" aria-hidden /> {item}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-auto pt-4 text-xs text-fg-subtle">{type.accepts}</p>
                    {!reason && (
                      <span className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700">
                        {type.to ? 'Start' : 'Choose and upload'} <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
                      </span>
                    )}
                  </div>
                )
                return (
                  <li key={type.id}>
                    {reason ? (
                      <div aria-disabled className="h-full cursor-not-allowed">
                        {card}
                      </div>
                    ) : (
                      <Link to={type.to ?? `/app/new?service=${type.id}`} className="group block h-full rounded-2xl focus:outline-none focus-visible:ring-3 focus-visible:ring-brand-200">
                        {card}
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
