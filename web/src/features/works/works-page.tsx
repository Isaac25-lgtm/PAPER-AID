import { HandCoins, NotebookPen, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Alert, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { INVITE_ONLY_REASON, NOT_CONFIGURED_REASON } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import type { Work, WorkKind } from '../../lib/work-types'
import { KIND_LABELS, ReadinessBadge, VARIANT_LABELS } from './shared'

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
    description: 'Concept notes and funding proposals written to the call: what it requires, read and quoted, and a draft checked against every rule.',
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
          <ButtonLink key={k} to={START[k]} size="sm" variant={k === 'FUNDING_PROPOSAL' ? 'secondary' : 'primary'}>
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
          action={offered[0] && <ButtonLink to={START[offered[0]]}><Plus className="size-4" aria-hidden /> Start</ButtonLink>}
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

const START: Record<WorkKind, string> = { COURSEWORK: '/app/start/coursework', CONCEPT_NOTE: '/app/start/concept-note', FUNDING_PROPOSAL: '/app/start/funding' }

/** New work starts with one Start (owner decision 2026-10-01): the earlier creation page is not offered. */
export function NewWorkPage() {
  const [params] = useSearchParams()
  const kind = (['CONCEPT_NOTE', 'COURSEWORK', 'FUNDING_PROPOSAL'].includes(params.get('kind') ?? '') ? params.get('kind') : 'COURSEWORK') as WorkKind
  return <Navigate to={START[kind]} replace />
}
