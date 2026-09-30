import { ArrowRight, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { TextArea } from '../../components/ui/field'
import { Alert, Badge } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatTokens } from '../../lib/format'
import type { Job, Stage } from '../../lib/types'
import { walletChanged } from '../../lib/use-wallet'
import type { Readiness, SourceRole, Variant, WorkKind, WorkStep, WorkStepQuote } from '../../lib/work-types'

export const KIND_LABELS: Record<WorkKind, string> = { CONCEPT_NOTE: 'Concept note', COURSEWORK: 'Coursework', FUNDING_PROPOSAL: 'Funding proposal' }

export const VARIANT_LABELS: Record<Variant, string> = {
  FUNDING_CONCEPT: 'Funding concept note',
  PROJECT_CONCEPT: 'Project concept note',
  ESSAY: 'Essay',
  ACADEMIC_REPORT: 'Academic report',
  CASE_STUDY_ANALYTICAL: 'Case study (analytical)',
  CASE_STUDY_PROBLEM: 'Case study (problem and recommendation)',
  LITERATURE_REVIEW: 'Literature review',
  RESEARCH_PAPER_EMPIRICAL: 'Short research paper (with data)',
  RESEARCH_PAPER_NON_EMPIRICAL: 'Short research paper (analytical)',
  REFLECTIVE: 'Reflective assignment',
  NGO_PROJECT: 'Project proposal (NGO or development)',
  RESEARCH_GRANT: 'Research grant proposal',
}

export const KIND_VARIANTS: Record<WorkKind, Variant[]> = {
  CONCEPT_NOTE: ['FUNDING_CONCEPT', 'PROJECT_CONCEPT'],
  COURSEWORK: ['ESSAY', 'ACADEMIC_REPORT', 'CASE_STUDY_ANALYTICAL', 'CASE_STUDY_PROBLEM', 'LITERATURE_REVIEW', 'RESEARCH_PAPER_EMPIRICAL', 'RESEARCH_PAPER_NON_EMPIRICAL', 'REFLECTIVE'],
  FUNDING_PROPOSAL: ['NGO_PROJECT', 'RESEARCH_GRANT'],
}

export const MODES: Record<WorkKind, { id: string; label: string }[]> = {
  CONCEPT_NOTE: [
    { id: 'BRIEF', label: 'Brief (about 900 words)' },
    { id: 'STANDARD', label: 'Standard (about 1,800 words; 1,500 for a project concept)' },
    { id: 'EXTENDED', label: 'Extended (about 2,900 words)' },
  ],
  COURSEWORK: [],
  FUNDING_PROPOSAL: [
    { id: 'COMPACT', label: 'Compact (about 2,500 words)' },
    { id: 'STANDARD', label: 'Standard (about 5,500 words)' },
    { id: 'COMPREHENSIVE', label: 'Comprehensive (about 10,000 words)' },
  ],
}

export const SOURCE_ROLES: Record<SourceRole, string> = {
  CALL: 'Call for proposals',
  TEMPLATE: 'Official template',
  ADDENDUM: 'Addendum or clarification',
  BRIEF: 'Assignment brief or question',
  RUBRIC: 'Marking rubric',
  READING: 'Reading',
  GUIDE: 'Handbook or guide',
  OTHER: 'Other document',
}

export function ReadinessBadge({ status }: { status: Readiness | null }) {
  if (status === 'READY') return <Badge tone="brand">Ready</Badge>
  if (status === 'READY_WITH_WARNINGS') return <Badge tone="warning">Ready with warnings</Badge>
  if (status === 'NOT_READY') return <Badge tone="danger">Not ready</Badge>
  return <Badge>Not written yet</Badge>
}

const STAGES: Partial<Record<Stage, string>> = {
  ANALYSING: 'Reading your documents',
  RESEARCHING: 'Researching the evidence',
  PLANNING: 'Planning',
  DRAFTING: 'Writing',
  AUDITING: 'Checking and improving',
  EXPORTING: 'Saving your work',
}

/** A running step, polled until it finishes. */
export function WorkProgress({ jobId, onDone }: { jobId: string; onDone: (job: Job | null) => void }) {
  const data = useData()
  const [job, setJob] = useState<Job | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let finished = false
    setBlocked(null)
    const stop = data.watchJob(
      jobId,
      (next) => {
        setJob(next)
        if ((!next || ['COMPLETED', 'FAILED', 'CANCELLED'].includes(next.status)) && !finished) {
          finished = true
          walletChanged()
          onDone(next)
        }
      },
      setBlocked,
    )
    return () => stop()
  }, [data, jobId, onDone, attempt])
  if (blocked)
    return (
      <Alert tone="warning" title="We lost track of this step" action={<Button size="sm" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>Check again</Button>}>
        {blocked} The step keeps running and its result is saved to your work.
      </Alert>
    )
  return (
    <div className="rounded-xl bg-brand-50 p-4 text-sm" aria-live="polite">
      <p className="flex items-center gap-2 font-semibold text-brand-900">
        <Loader2 className="size-4 animate-spin" aria-hidden /> {job?.stage ? (STAGES[job.stage] ?? 'Working') : 'Queued'}
      </p>
      <p className="mt-1 text-brand-800">This takes a few minutes. You can leave this page; the result is saved to your work.</p>
    </div>
  )
}

/** Price a step, show what the student must know, then start it. */
export function WorkStepRunner({
  workId,
  step,
  label,
  description,
  onStarted,
  disabledReason,
  withNote = true,
}: {
  workId: string
  step: WorkStep
  label: string
  description: string
  onStarted: (jobId: string) => void
  disabledReason?: string | null
  withNote?: boolean
}) {
  const data = useData()
  const charging = data.config.creditsEnabled
  const [note, setNote] = useState('')
  const [quote, setQuote] = useState<WorkStepQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const price = async () => {
    setBusy(true)
    setError(null)
    try {
      setQuote(await data.works.quoteStep(workId, step, note))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not price this step.')
    } finally {
      setBusy(false)
    }
  }
  const start = async () => {
    if (!quote) return
    setBusy(true)
    setError(null)
    try {
      await data.works.submitStep(workId, quote.job.id, quote.quote.id)
      walletChanged()
      onStarted(quote.job.id)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start this step.')
      setQuote(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-line p-4">
      <p className="text-sm font-semibold">{label}</p>
      <p className="mt-1 text-sm text-fg-muted">{disabledReason ?? description}</p>
      {!disabledReason && (
        <>
          {withNote && (
            <TextArea
              className="mt-3"
              label="Anything PaperAid should know for this run? (optional)"
              rows={2}
              maxLength={1000}
              value={note}
              onChange={(e) => {
                setNote(e.target.value)
                setQuote(null)
              }}
            />
          )}
          {error && (
            <Alert tone="warning" className="mt-3">
              {error}
            </Alert>
          )}
          {quote ? (
            <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm">
              {quote.notice && (
                <Alert tone="info" className="mb-3">
                  {quote.notice}
                </Alert>
              )}
              {quote.quote.lines.map((l) => (
                <p key={l.label} className="flex justify-between gap-3">
                  <span className="text-fg-muted">{l.label}</span> <span className="font-medium whitespace-nowrap">{formatTokens(l.amount)}</span>
                </p>
              ))}
              <p className="mt-2 text-xs text-fg-subtle">
                {charging ? 'If PaperAid cannot deliver this step, nothing is charged. Never more than this.' : 'Not charged while PaperAid is in testing.'}
              </p>
              <Button className="mt-3 w-full" loading={busy} onClick={start}>
                Start <ArrowRight className="size-4" aria-hidden />
              </Button>
            </div>
          ) : (
            <Button className="mt-3" variant="secondary" loading={busy} onClick={price}>
              See the price
            </Button>
          )}
        </>
      )}
    </div>
  )
}

export function money(value: number, currency: string) {
  return `${currency} ${value.toLocaleString('en-GB', { maximumFractionDigits: 2 })}`.trim()
}
