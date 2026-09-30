import { HandCoins, NotebookPen, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Input, Select, TextArea } from '../../components/ui/field'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { INVITE_ONLY_REASON, NOT_CONFIGURED_REASON } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import type { Variant, Work, WorkCitation, WorkKind } from '../../lib/work-types'
import { KIND_LABELS, KIND_VARIANTS, MODES, ReadinessBadge, VARIANT_LABELS } from './shared'

/** Coursework, or Funding (concept notes and funding proposals): the two new sections. */
export type Section = 'COURSEWORK' | 'FUNDING'
const SECTION_KINDS: Record<Section, WorkKind[]> = { COURSEWORK: ['COURSEWORK'], FUNDING: ['CONCEPT_NOTE', 'FUNDING_PROPOSAL'] }
const SECTION_TEXT: Record<Section, { title: string; description: string }> = {
  COURSEWORK: {
    title: 'Coursework',
    description: 'Essays, reports, case studies, literature reviews, short research papers and reflective work, planned from your brief and written from confirmed sources.',
  },
  FUNDING: {
    title: 'Funding',
    description: 'Concept notes and funding proposals built from the call: what it requires, a plan you approve, and a draft checked against every rule.',
  },
}

function reason(availability: string | undefined) {
  if (availability === 'invite_only') return INVITE_ONLY_REASON
  if (availability === 'not_configured') return NOT_CONFIGURED_REASON
  if (availability === 'soon' || !availability) return 'Coming soon.'
  return null
}

export function WorksPage() {
  const [params] = useSearchParams()
  const section: Section = params.get('section') === 'FUNDING' ? 'FUNDING' : 'COURSEWORK'
  useTitle(SECTION_TEXT[section].title)
  const data = useData()
  const [works, setWorks] = useState<Work[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const kinds = SECTION_KINDS[section]
  const offered = kinds.filter((k) => data.config.availability[k] === 'available')

  useEffect(() => {
    data.works
      .list()
      .then((all) => setWorks(all.filter((w) => kinds.includes(w.kind))))
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load your work.'))
  }, [data, section]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader
        title={SECTION_TEXT[section].title}
        description={SECTION_TEXT[section].description}
        actions={offered.map((k) => (
          <ButtonLink key={k} to={`/app/works/new?kind=${k}`} size="sm" variant={k === 'FUNDING_PROPOSAL' ? 'secondary' : 'primary'}>
            <Plus className="size-4" aria-hidden /> New {KIND_LABELS[k].toLowerCase()}
          </ButtonLink>
        ))}
      />
      {offered.length === 0 && (
        <Alert tone="info" className="mb-5">
          {reason(data.config.availability[kinds[0]])}
        </Alert>
      )}
      {error && (
        <Alert tone="danger" className="mb-5">
          {error}
        </Alert>
      )}
      {works === null && !error ? (
        <div className="space-y-3">
          <Skeleton className="h-24 rounded-2xl" />
        </div>
      ) : works && works.length === 0 ? (
        <EmptyState
          icon={section === 'COURSEWORK' ? <NotebookPen className="size-6" aria-hidden /> : <HandCoins className="size-6" aria-hidden />}
          title="Nothing here yet"
          action={offered[0] && <ButtonLink to={`/app/works/new?kind=${offered[0]}`}><Plus className="size-4" aria-hidden /> Start</ButtonLink>}
        >
          {section === 'COURSEWORK'
            ? 'Start from your assignment question. PaperAid reads it and your brief, shows what it understood, and plans the answer with you before anything is written.'
            : 'Start from your idea and the call. PaperAid reads the call, shows what it requires, and plans the document with you before anything is written.'}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {works?.map((w) => (
            <li key={w.id}>
              <Link to={`/app/works/${w.id}`} className="block rounded-2xl border border-line bg-white p-5 shadow-card transition-colors hover:border-brand-300">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-fg">{w.plan?.title ?? w.inputs.title}</p>
                  <ReadinessBadge status={w.status} />
                </div>
                <p className="mt-1 text-sm text-fg-muted">
                  {VARIANT_LABELS[w.variant]} · {w.documents.length ? `${w.documents.length} version${w.documents.length === 1 ? '' : 's'}` : w.plan ? 'Planned' : 'Being set up'}
                </p>
                <p className="mt-1 text-xs text-fg-subtle">Kept until {formatDate(w.expiresAt)} unless you work on it again.</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export function NewWorkPage() {
  const [params] = useSearchParams()
  const kind = (['CONCEPT_NOTE', 'COURSEWORK', 'FUNDING_PROPOSAL'].includes(params.get('kind') ?? '') ? params.get('kind') : 'COURSEWORK') as WorkKind
  useTitle(`New ${KIND_LABELS[kind].toLowerCase()}`)
  const data = useData()
  const navigate = useNavigate()
  const variants = KIND_VARIANTS[kind]
  const [variant, setVariant] = useState<Variant>((params.get('variant') as Variant) ?? variants[0])
  const [mode, setMode] = useState(MODES[kind][1]?.id ?? '')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [citation, setCitation] = useState<WorkCitation>('APA7')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blocked = reason(data.config.availability[kind])
  const coursework = kind === 'COURSEWORK'

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const work = await data.works.create(kind, variant, mode, { title, description, answers: {}, experience: '' }, citation)
      navigate(`/app/works/${work.id}`)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start this.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title={`New ${KIND_LABELS[kind].toLowerCase()}`}
        description={
          coursework
            ? 'Tell PaperAid what you have been asked to write. On the next page you can add your brief, rubric and readings.'
            : 'Tell PaperAid about your idea. On the next page you can add the call or template, and PaperAid reads its requirements.'
        }
      />
      {blocked ? (
        <Alert tone="info">{blocked}</Alert>
      ) : (
        <Card className="max-w-3xl space-y-4 p-5">
          <Select label={coursework ? 'Type of assignment' : 'What are you preparing?'} value={variant} onChange={(e) => setVariant(e.target.value as Variant)}>
            {variants.map((v) => (
              <option key={v} value={v}>
                {VARIANT_LABELS[v]}
              </option>
            ))}
          </Select>
          {MODES[kind].length > 0 && (
            <Select label="Length" value={mode} onChange={(e) => setMode(e.target.value)} hint="A call's own limit always replaces this.">
              {MODES[kind].map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </Select>
          )}
          <Input label={coursework ? 'Title or topic' : 'Project name or topic'} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />
          <TextArea
            label={coursework ? 'The assignment question, word for word' : 'Your idea: the problem, who it affects and what you propose'}
            rows={5}
            maxLength={8000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            hint={coursework ? 'Every part of it. You can also upload the brief on the next page.' : 'Your own words are enough. PaperAid finds the evidence.'}
          />
          {coursework && (
            <Select label="Referencing style" value={citation} onChange={(e) => setCitation(e.target.value as WorkCitation)} hint="Your brief's style always wins if it names one.">
              <option value="APA7">APA 7th edition</option>
              <option value="APA6">APA 6th edition</option>
              <option value="HARVARD">Harvard</option>
            </Select>
          )}
          {error && <Alert tone="danger">{error}</Alert>}
          <Button size="lg" loading={busy} disabled={title.trim().length < 3} onClick={create}>
            Continue
          </Button>
        </Card>
      )}
    </>
  )
}
