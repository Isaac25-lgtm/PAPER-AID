import { FileSearch, GraduationCap, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Input, Select, TextArea } from '../../components/ui/field'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import type { CitationStyle, Level, Project, ProposalInputs, Rulebook, StudyType, TitlePage } from '../../lib/proposal-types'
import { INVITE_ONLY_REASON, NOT_CONFIGURED_REASON } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import { LEVELS, PlanStatusBadge, STUDY_TYPES } from './shared'

function unavailableReason(availability: string) {
  if (availability === 'invite_only') return INVITE_ONLY_REASON
  if (availability === 'not_configured') return NOT_CONFIGURED_REASON
  if (availability === 'soon') return 'Research proposals are coming soon.'
  return null
}

export function ProjectsPage() {
  useTitle('Research proposals')
  const data = useData()
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const blocked = unavailableReason(data.config.availability.PROPOSAL)

  useEffect(() => {
    data.projects
      .list()
      .then(setProjects)
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load your proposals.'))
  }, [data])

  return (
    <>
      <PageHeader
        title="Research proposals"
        description="Plan, research and write your research proposal chapter by chapter, or check one you have already written."
        actions={
          !blocked && (
            <ButtonLink to="/app/projects/new">
              <Plus className="size-4" aria-hidden /> New proposal
            </ButtonLink>
          )
        }
      />
      {blocked && (
        <Alert tone="info" className="mb-5">
          {blocked}
        </Alert>
      )}
      {error && (
        <Alert tone="danger" className="mb-5">
          {error}
        </Alert>
      )}
      <Card className="mb-6 flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-3">
          <FileSearch className="mt-0.5 size-5 shrink-0 text-brand-700" aria-hidden />
          <div>
            <p className="text-sm font-semibold">Already written a proposal?</p>
            <p className="text-sm text-fg-muted">PaperAid checks it for missing sections, alignment, tense, references and what a supervisor is likely to raise.</p>
          </div>
        </div>
        <ButtonLink to="/app/new?review=1" variant="secondary" size="sm">
          Review my proposal
        </ButtonLink>
      </Card>
      {projects === null && !error ? (
        <div className="space-y-3">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
        </div>
      ) : projects && projects.length === 0 ? (
        <EmptyState
          icon={<GraduationCap className="size-6" aria-hidden />}
          title="No proposals yet"
          action={
            !blocked && (
              <ButtonLink to="/app/projects/new">
                <Plus className="size-4" aria-hidden /> Start a proposal
              </ButtonLink>
            )
          }
        >
          Start from your topic. PaperAid researches the evidence and drafts a plan for you to edit and approve, then writes each chapter from it.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {projects?.map((p) => (
            <li key={p.id}>
              <Link to={`/app/projects/${p.id}`} className="block rounded-2xl border border-line bg-white p-5 shadow-card transition-colors hover:border-brand-300">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-fg">{p.plan?.title ?? p.inputs.topic}</p>
                  <PlanStatusBadge status={p.planStatus} />
                </div>
                <p className="mt-1 text-sm text-fg-muted">
                  {LEVELS[p.inputs.level]} · {p.chapters.filter((c) => c.current).length} of 3 chapters written · {p.evidenceCount} confirmed sources
                </p>
                <p className="mt-1 text-xs text-fg-subtle">Kept until {formatDate(p.expiresAt)} unless you work on it again.</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

const EMPTY_INPUTS: ProposalInputs = {
  topic: '',
  level: 'MASTERS',
  programme: '',
  faculty: '',
  studyArea: '',
  population: '',
  studyType: null,
  notes: '',
  populationSize: null,
  populationSource: '',
  expectedParticipants: null,
}
const EMPTY_TITLE: TitlePage = { studentName: '', regNumber: '', supervisor: '', submissionDate: '' }

/** The study details and title page, used when creating a project and on its Details tab. */
export function DetailsForm({
  initial,
  titlePage,
  citation,
  rulebook,
  submitLabel,
  onSubmit,
}: {
  initial: ProposalInputs
  titlePage: TitlePage
  citation: CitationStyle
  rulebook: Rulebook | null
  submitLabel: string
  onSubmit: (inputs: ProposalInputs, titlePage: TitlePage, citation: CitationStyle) => Promise<void>
}) {
  const [inputs, setInputs] = useState(initial)
  const [page, setPage] = useState(titlePage)
  const [style, setStyle] = useState(citation)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<ProposalInputs>) => setInputs((i) => ({ ...i, ...patch }))

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSubmit(inputs, page, style)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not save these details.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <Card className="space-y-4 p-5">
        <p className="text-base font-semibold">Your study</p>
        <TextArea label="Topic" rows={2} value={inputs.topic} maxLength={300} onChange={(e) => set({ topic: e.target.value })} hint="A working title or a sentence describing what you want to study." />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Level" value={inputs.level} onChange={(e) => set({ level: e.target.value as Level })}>
            {Object.entries(LEVELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
                {rulebook ? ` (${rulebook.levels[id as Level].pages[0]}–${rulebook.levels[id as Level].pages[1]} pages)` : ''}
              </option>
            ))}
          </Select>
          <Select label="Type of study" value={inputs.studyType ?? ''} onChange={(e) => set({ studyType: (e.target.value || null) as StudyType | null })}>
            <option value="">Not sure yet: PaperAid will propose one</option>
            {Object.entries(STUDY_TYPES).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </Select>
          <Input label="Programme" value={inputs.programme} maxLength={150} onChange={(e) => set({ programme: e.target.value })} placeholder="e.g. Master of Public Health" />
          <Input label="Faculty or school" value={inputs.faculty} maxLength={150} onChange={(e) => set({ faculty: e.target.value })} />
          <Input label="Study area (if known)" value={inputs.studyArea} maxLength={200} onChange={(e) => set({ studyArea: e.target.value })} />
          <Input label="Study population (if known)" value={inputs.population} maxLength={200} onChange={(e) => set({ population: e.target.value })} />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            label="Accessible population (if known)"
            type="number"
            min={1}
            value={inputs.populationSize ?? ''}
            onChange={(e) => set({ populationSize: e.target.value ? Number(e.target.value) : null })}
            hint="Only a figure you have: PaperAid never supplies it."
          />
          <Input label="Where that figure comes from" value={inputs.populationSource} maxLength={300} onChange={(e) => set({ populationSource: e.target.value })} placeholder="e.g. district records, 2025" />
          <Input
            label="Expected participants (qualitative)"
            type="number"
            min={1}
            value={inputs.expectedParticipants ?? ''}
            onChange={(e) => set({ expectedParticipants: e.target.value ? Number(e.target.value) : null })}
          />
        </div>
        <TextArea
          label="What you already have (optional)"
          rows={4}
          maxLength={4000}
          value={inputs.notes}
          onChange={(e) => set({ notes: e.target.value })}
          hint="A concept summary, your supervisor's guidance, decisions already made."
        />
      </Card>
      <Card className="space-y-4 p-5">
        <div>
          <p className="text-base font-semibold">Title page</p>
          <p className="mt-0.5 text-sm text-fg-muted">Only printed on the title page. These details are never sent to an AI model or a search. You can add them later.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Your name" value={page.studentName} maxLength={120} onChange={(e) => setPage({ ...page, studentName: e.target.value })} />
          <Input label="Registration number" value={page.regNumber} maxLength={60} onChange={(e) => setPage({ ...page, regNumber: e.target.value })} />
          <Input label="Proposed supervisor" value={page.supervisor} maxLength={160} onChange={(e) => setPage({ ...page, supervisor: e.target.value })} />
          <Input label="Submission date" value={page.submissionDate} maxLength={40} onChange={(e) => setPage({ ...page, submissionDate: e.target.value })} placeholder="e.g. October 2026" />
        </div>
        <Select
          label="Citation style"
          value={style}
          onChange={(e) => setStyle(e.target.value as CitationStyle)}
          hint="Choose the edition your faculty uses. You can switch at any time."
        >
          {Object.entries({ APA6: 'APA 6th edition', APA7: 'APA 7th edition' }).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </Select>
      </Card>
      {error && <Alert tone="danger">{error}</Alert>}
      <Button size="lg" loading={busy} disabled={inputs.topic.trim().length < 10} onClick={submit}>
        {submitLabel}
      </Button>
    </div>
  )
}

export function NewProjectPage() {
  useTitle('New proposal')
  const data = useData()
  const navigate = useNavigate()
  const [rulebook, setRulebook] = useState<Rulebook | null>(null)
  useEffect(() => {
    data.projects.rulebook().then(setRulebook).catch(() => setRulebook(null))
  }, [data])
  return (
    <>
      <PageHeader
        title="New research proposal"
        description={
          <>
            Tell PaperAid about your study. It researches the evidence and drafts a plan for you to edit and approve before any chapter is written.
          </>
        }
      />
      <div className="max-w-3xl">
        <DetailsForm
          initial={EMPTY_INPUTS}
          titlePage={EMPTY_TITLE}
          citation={rulebook?.defaultCitation ?? 'APA6'}
          rulebook={rulebook}
          submitLabel="Create proposal"
          onSubmit={async (inputs, titlePage, citation) => {
            const project = await data.projects.create(inputs, titlePage, citation)
            navigate(`/app/projects/${project.id}`)
          }}
        />
      </div>
    </>
  )
}
