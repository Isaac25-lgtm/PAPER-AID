import { clsx } from 'clsx'
import { ArrowRight, Bot, CheckCircle2, CircleDashed, Loader2, MinusCircle, ShieldCheck, TriangleAlert, User, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { TextArea } from '../../components/ui/field'
import { Alert, Badge } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatUGX } from '../../lib/format'
import type { ReadinessItem, ReadinessStatus, StepId, StepQuote } from '../../lib/proposal-types'
import type { Job, Stage } from '../../lib/types'
import { walletChanged } from '../../lib/use-wallet'

export const LEVELS = { BACHELORS: "Bachelor's", PGD: 'Postgraduate Diploma', MASTERS: "Master's", PHD: 'PhD' } as const
export const STUDY_TYPES = {
  QUANTITATIVE: 'Quantitative',
  QUALITATIVE: 'Qualitative',
  MIXED: 'Mixed methods',
  SECONDARY: 'Secondary data',
  NON_EMPIRICAL: 'Non-empirical (theoretical, textual)',
} as const

const STATUS: Record<ReadinessStatus, { label: string; icon: typeof CheckCircle2; className: string }> = {
  PASS: { label: 'Pass', icon: CheckCircle2, className: 'text-brand-700' },
  NEEDS_REVIEW: { label: 'Needs review', icon: TriangleAlert, className: 'text-amber-700' },
  MISSING: { label: 'Missing', icon: XCircle, className: 'text-red-600' },
  NOT_APPLICABLE: { label: 'Not applicable', icon: MinusCircle, className: 'text-fg-subtle' },
  BLOCKED: { label: 'Blocked', icon: CircleDashed, className: 'text-red-600' },
}
const BASIS = {
  CODE: { label: 'PaperAid check', icon: ShieldCheck },
  AI: { label: 'AI judgement', icon: Bot },
  AUTHOR: { label: 'Your information', icon: User },
} as const

/** A checklist, never a mark: each item says who settled it (a code check, the AI, or the student). */
export function ReadinessList({ items }: { items: ReadinessItem[] }) {
  const passed = items.filter((i) => i.status === 'PASS' || i.status === 'NOT_APPLICABLE').length
  return (
    <div>
      <p className="text-sm text-fg-muted">
        {passed} of {items.length} checks pass. This follows the UCU manual&rsquo;s vetting questions; it is not a mark, and PaperAid does not check plagiarism.
      </p>
      <ul className="mt-3 divide-y divide-line rounded-xl border border-line">
        {items.map((item) => {
          const status = STATUS[item.status]
          const basis = BASIS[item.basis]
          return (
            <li key={item.id} className="flex gap-3 p-3">
              <status.icon className={clsx('mt-0.5 size-4 shrink-0', status.className)} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg">{item.question}</p>
                {item.note && <p className="mt-0.5 text-xs leading-relaxed text-fg-muted">{item.note}</p>}
                {item.where && <p className="mt-0.5 text-xs text-fg-subtle">{item.where}</p>}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1 text-right">
                <span className={clsx('text-xs font-semibold', status.className)}>{status.label}</span>
                <span className="flex items-center gap-1 text-[11px] text-fg-subtle">
                  <basis.icon className="size-3" aria-hidden /> {basis.label}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const STEP_STAGES: Partial<Record<Stage, string>> = {
  RESEARCHING: 'Researching: planning what evidence is needed, then reading sources',
  PLANNING: 'Planning: the lead adviser drafts, a second adviser critiques, the lead finalises',
  DRAFTING: 'Writing the sections from your plan and the confirmed evidence',
  AUDITING: 'Checking every citation and figure, reviewing and fixing',
  EXPORTING: 'Saving to your proposal',
}

/** A running step's progress, polled until it finishes. */
export function StepProgress({ jobId, onDone }: { jobId: string; onDone: (job: Job | null) => void }) {
  const data = useData()
  const [job, setJob] = useState<Job | null>(null)
  useEffect(() => {
    let finished = false
    const stop = data.watchJob(jobId, (next) => {
      setJob(next)
      if (!next || ['COMPLETED', 'FAILED', 'CANCELLED'].includes(next.status)) {
        if (!finished) {
          finished = true
          walletChanged()
          onDone(next)
        }
      }
    })
    return () => stop()
  }, [data, jobId, onDone])
  return (
    <div className="rounded-xl bg-brand-50 p-4 text-sm" aria-live="polite">
      <p className="flex items-center gap-2 font-semibold text-brand-900">
        <Loader2 className="size-4 animate-spin" aria-hidden /> {job?.stage ? (STEP_STAGES[job.stage] ?? 'Working') : 'Queued'}
      </p>
      <p className="mt-1 text-brand-800">This takes a few minutes. You can leave this page; the result is saved to your proposal.</p>
    </div>
  )
}

/** Price a step, let the student add a note, then start it. */
export function StepRunner({
  projectId,
  step,
  label,
  description,
  onStarted,
  disabledReason,
}: {
  projectId: string
  step: StepId
  label: string
  description: string
  onStarted: (jobId: string) => void
  disabledReason?: string
}) {
  const data = useData()
  const charging = data.config.creditsEnabled
  const [note, setNote] = useState('')
  const [quote, setQuote] = useState<StepQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const price = async () => {
    setBusy(true)
    setError(null)
    try {
      setQuote(await data.projects.quoteStep(projectId, step, note))
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
      await data.projects.submitStep(projectId, quote.job.id, quote.quote.id)
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
            hint="For example your supervisor's comments. It guides this run only; your approved plan is never changed by it."
          />
          {error && (
            <Alert tone="warning" className="mt-3">
              {error}
            </Alert>
          )}
          {quote ? (
            <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm">
              {quote.quote.lines.map((l) => (
                <p key={l.label} className="flex justify-between gap-3">
                  <span className="text-fg-muted">{l.label}</span> <span className="font-medium whitespace-nowrap">{formatUGX(l.amount)}</span>
                </p>
              ))}
              <p className="mt-2 text-xs text-fg-subtle">
                {charging ? 'You are charged for the work actually done, never more than this.' : 'Not charged while PaperAid is in testing.'}
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

export function PlanStatusBadge({ status }: { status: 'NONE' | 'DRAFT' | 'APPROVED' }) {
  if (status === 'APPROVED') return <Badge tone="brand">Approved</Badge>
  if (status === 'DRAFT') return <Badge tone="warning">Draft: review and approve</Badge>
  return <Badge>Not started</Badge>
}
