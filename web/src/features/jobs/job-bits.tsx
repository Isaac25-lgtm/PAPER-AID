import { clsx } from 'clsx'
import { AlertTriangle, Check, ChevronRight, Circle, FileText, Loader2 } from 'lucide-react'
import { Link } from 'react-router'
import { Badge, type Tone } from '../../components/ui/primitives'
import { formatRelative, formatUGX } from '../../lib/format'
import { SERVICES, STAGE_LABELS, STATUS_LABELS } from '../../lib/services'
import type { Job } from '../../lib/types'

export function StatusBadge({ job }: { job: Pick<Job, 'status' | 'outcome' | 'expiresAt'> }) {
  if (job.status === 'COMPLETED' && new Date(job.expiresAt).getTime() < Date.now())
    return <Badge tone="neutral">Files expired</Badge>
  if (job.status === 'COMPLETED' && job.outcome === 'PARTIAL')
    return (
      <Badge tone="warning">
        <AlertTriangle className="size-3" aria-hidden /> Ready · with warnings
      </Badge>
    )
  const tones: Record<Job['status'], Tone> = {
    DRAFT: 'neutral',
    QUOTED: 'neutral',
    AWAITING_PAYMENT: 'warning',
    QUEUED: 'info',
    PROCESSING: 'violet',
    COMPLETED: 'brand',
    FAILED: 'danger',
    CANCELLED: 'neutral',
  }
  return (
    <Badge tone={tones[job.status]}>
      {job.status === 'PROCESSING' && <Loader2 className="size-3 animate-spin" aria-hidden />}
      {job.status === 'COMPLETED' && <Check className="size-3" aria-hidden />}
      {STATUS_LABELS[job.status]}
    </Badge>
  )
}

export const serviceNames = (job: Pick<Job, 'services'>) => job.services.map((s) => SERVICES[s].name).join(' + ')

export function JobRow({ job }: { job: Job }) {
  return (
    <li>
      <Link
        to={`/app/jobs/${job.id}`}
        className="group flex items-center gap-4 rounded-xl px-3 py-3.5 transition-colors hover:bg-surface-subtle sm:px-4"
      >
        <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-fg">{job.source.name}</p>
          <p className="mt-0.5 truncate text-xs text-fg-subtle">
            {serviceNames(job)} · {formatRelative(job.createdAt)}
          </p>
          <div className="mt-1.5 sm:hidden">
            <StatusBadge job={job} />
          </div>
        </div>
        <div className="hidden text-right text-sm text-fg-muted sm:block">{formatUGX(job.quote.amount)}</div>
        <div className="hidden sm:block">
          <StatusBadge job={job} />
        </div>
        <ChevronRight className="size-4 shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5" aria-hidden />
      </Link>
    </li>
  )
}

type StepState = 'done' | 'current' | 'upcoming'

export function StageTimeline({ job }: { job: Job }) {
  const currentIndex = job.stage ? job.pipeline.indexOf(job.stage) : -1
  const steps: { label: string; state: StepState }[] = [
    { label: 'Queued', state: job.status === 'QUEUED' ? 'current' : 'done' },
    ...job.pipeline.map((stage, i): { label: string; state: StepState } => {
      let state: StepState = 'upcoming'
      if (job.status === 'COMPLETED' || (job.status === 'PROCESSING' && i < currentIndex)) state = 'done'
      if (job.status === 'PROCESSING' && i === currentIndex) state = 'current'
      return { label: STAGE_LABELS[stage], state }
    }),
    { label: 'Ready to download', state: job.status === 'COMPLETED' ? 'done' : 'upcoming' },
  ]

  return (
    <ol className="space-y-0" aria-label="Job progress">
      {steps.map((step, i) => (
        <li key={step.label} className="relative flex gap-3 pb-5 last:pb-0">
          {i < steps.length - 1 && (
            <span aria-hidden className={clsx('absolute top-7 bottom-0 left-[13px] w-0.5', step.state === 'done' ? 'bg-brand-400' : 'bg-line')} />
          )}
          <span
            className={clsx(
              'relative grid size-7 shrink-0 place-items-center rounded-full ring-4 ring-white',
              step.state === 'done' && 'bg-brand-600 text-white',
              step.state === 'current' && 'bg-brand-50 text-brand-700 ring-brand-100',
              step.state === 'upcoming' && 'bg-surface-muted text-fg-subtle',
            )}
          >
            {step.state === 'done' && <Check className="size-4" aria-hidden />}
            {step.state === 'current' && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {step.state === 'upcoming' && <Circle className="size-2 fill-current" aria-hidden />}
          </span>
          <div className="pt-0.5">
            <p className={clsx('text-sm', step.state === 'current' ? 'font-semibold text-fg' : step.state === 'done' ? 'text-fg' : 'text-fg-subtle')}>
              {step.label}
            </p>
            {step.state === 'current' && <p className="text-xs text-brand-700">In progress</p>}
            <span className="sr-only">{step.state === 'done' ? '(complete)' : step.state === 'current' ? '(in progress)' : '(not started)'}</span>
          </div>
        </li>
      ))}
    </ol>
  )
}
