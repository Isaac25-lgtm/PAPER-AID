import { clsx } from 'clsx'
import { Check, Circle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Alert, Card } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { Job } from '../../lib/types'
import { walletChanged } from '../../lib/use-wallet'

export type Phase = 'read' | 'plan' | 'write'

const STEPS = ['Reading your documents', 'Finding and checking sources', 'Planning', 'Writing', 'Checking every requirement']

/** Where a running job is in the whole journey: the plan step covers sources and planning, the
 *  writing step writing and checking (both research again before they write). */
function position(job: Job | null, phase: Phase): number {
  if (phase === 'read') return 0
  const stage = job?.stage
  if (phase === 'plan') return stage === 'PLANNING' ? 2 : 1
  if (stage === 'AUDITING' || stage === 'EXPORTING' || stage === 'FORMATTING') return 4
  return 3
}

/** The progress screen (owner decision 2026-10-01): plain steps, an honest estimate for the service,
 *  safe to close, and a stop request that reports what actually happened. */
export function StartProgress({ jobId, phase, title, estimate, onDone }: { jobId: string; phase: Phase; title: string; estimate: string; onDone: (job: Job | null) => void }) {
  const data = useData()
  const [job, setJob] = useState<Job | null>(null)
  const [lost, setLost] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState<string | null>(null)
  useEffect(() => {
    let finished = false
    setLost(null)
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
      setLost,
    )
    return () => stop()
  }, [data, jobId, onDone, attempt])

  const requestStop = async () => {
    if (!window.confirm('Stop now? Nothing will be delivered for this, and anything reserved for it is returned.')) return
    setStopping(true)
    setStopError(null)
    try {
      await data.cancelJob(jobId)
    } catch (e) {
      setStopError(e instanceof DataError ? e.message : 'It could not be stopped right now. It keeps running.')
      setStopping(false)
    }
  }

  const at = position(job, phase)
  return (
    <Card className="mx-auto max-w-2xl p-6 sm:p-8">
      <h1 className="text-xl font-bold text-fg sm:text-2xl">{title}</h1>
      <ol className="mt-6 space-y-3" aria-live="polite">
        {STEPS.map((step, i) => {
          const done = i < at
          const now = i === at
          return (
            <li key={step} className="flex items-center gap-3 text-sm">
              <span
                className={clsx(
                  'grid size-7 shrink-0 place-items-center rounded-full',
                  done ? 'bg-brand-600 text-white' : now ? 'bg-brand-50 text-brand-700 ring-2 ring-brand-300' : 'bg-surface-muted text-fg-subtle',
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : now ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Circle className="size-3" aria-hidden />}
              </span>
              <span className={clsx(now ? 'font-semibold text-fg' : done ? 'text-fg-muted' : 'text-fg-subtle')}>
                {step}
                {now && <span className="sr-only"> (in progress)</span>}
                {done && <span className="sr-only"> (done)</span>}
              </span>
            </li>
          )
        })}
      </ol>
      <p className="mt-6 text-sm text-fg-muted">
        {estimate} You can close this page: your work is saved and will be on your dashboard when it is ready.
      </p>
      {lost && (
        <Alert tone="warning" className="mt-4" action={<Button size="sm" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>Check again</Button>}>
          {lost} PaperAid keeps working and saves the result to your work.
        </Alert>
      )}
      {stopError && (
        <Alert tone="warning" className="mt-4">
          {stopError}
        </Alert>
      )}
      <div className="mt-6 flex flex-wrap gap-2">
        <Link to="/app" className="inline-flex min-h-10 items-center rounded-lg border border-line bg-white px-4 text-sm font-semibold text-fg hover:bg-surface-muted">
          Go to dashboard
        </Link>
        <Button variant="ghost" loading={stopping} onClick={requestStop}>
          {stopping ? 'Stopping…' : 'Request stop'}
        </Button>
      </div>
    </Card>
  )
}

/** Why a one-Start job stopped without a document, with the way forward. */
export function StoppedCard({ message, onRetry, busy, error, title = "We couldn't finish this one", retryLabel = 'Try again' }: {
  message: string; onRetry: () => void; busy: boolean; error: string | null; title?: string; retryLabel?: string
}) {
  return (
    <Card className="mx-auto max-w-2xl p-6 sm:p-8">
      <h1 className="text-xl font-bold text-fg">{title}</h1>
      <p className="mt-2 text-sm text-fg-muted">{message}</p>
      {error && (
        <Alert tone="warning" className="mt-4">
          {error}
        </Alert>
      )}
      <div className="mt-5 flex flex-wrap gap-2">
        <Button loading={busy} onClick={onRetry}>
          {retryLabel}
        </Button>
        <Link to="/app" className="inline-flex min-h-10 items-center rounded-lg border border-line bg-white px-4 text-sm font-semibold text-fg hover:bg-surface-muted">
          Go to dashboard
        </Link>
      </div>
    </Card>
  )
}
