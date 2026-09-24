import { ArrowLeft, CircleSlash, Clock, Copy, FileSearch, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Dialog, Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/overlays'
import { Alert, Card, EmptyState, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate, formatDateTime, formatUGX } from '../../lib/format'
import type { Job } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { BandChange, ChangesPanel, DownloadList, FindingsList, FormattingPanel, ScoreCard } from '../results/report'
import { useJob } from './hooks'
import { serviceNames, StageTimeline, StatusBadge } from './job-bits'

const isTerminal = (j: Job) => j.status === 'COMPLETED' || j.status === 'FAILED' || j.status === 'CANCELLED'

export function JobPage() {
  const { jobId = '' } = useParams()
  const { job, loading } = useJob(jobId)
  useTitle(job?.source.name ?? 'Job')

  if (loading) return <JobSkeleton />
  if (!job)
    return (
      <EmptyState icon={<FileSearch className="size-5" />} title="We couldn't find this job" action={<ButtonLink to="/app">Back to dashboard</ButtonLink>}>
        It may have been deleted, or the link may be wrong.
      </EmptyState>
    )

  return (
    <>
      <Link to="/app/history" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> All jobs
      </Link>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-bold break-words sm:text-2xl">{job.source.name}</h1>
          <p className="mt-1 text-sm text-fg-muted">
            {serviceNames(job)} · Submitted {formatDateTime(job.createdAt)}
          </p>
        </div>
        <div className="shrink-0 self-start">
          <StatusBadge job={job} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-6">
          <JobBody job={job} />
        </div>
        <aside className="space-y-4">
          <JobDetails job={job} />
        </aside>
      </div>
    </>
  )
}

function JobBody({ job }: { job: Job }) {
  if (job.status === 'QUEUED' || job.status === 'PROCESSING') return <InProgress job={job} />
  if (job.status === 'FAILED')
    return (
      <Alert
        tone="danger"
        title="This job didn't finish"
        action={
          <div className="flex flex-wrap gap-2">
            <ButtonLink to="/app/new" size="sm" variant="secondary">
              Start a new job
            </ButtonLink>
          </div>
        }
      >
        <p>{job.failure?.userMessage}</p>
        <p className="mt-2">
          {job.paymentStatus === 'BETA_BYPASS' ? 'Beta jobs are free, so nothing was charged.' : 'You have not been charged for this job.'}{' '}
          {job.failure?.retryable && 'We may restart it for you — it will appear here if we do.'}
        </p>
      </Alert>
    )
  if (job.status === 'CANCELLED')
    return (
      <Card className="flex items-center gap-4 p-6">
        <CircleSlash className="size-6 shrink-0 text-fg-subtle" aria-hidden />
        <div>
          <p className="font-semibold">This job was cancelled before it started.</p>
          <p className="text-sm text-fg-muted">Nothing was processed or charged.</p>
        </div>
      </Card>
    )
  return <Completed job={job} />
}

function InProgress({ job }: { job: Job }) {
  const data = useData()
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cancel = async () => {
    setBusy(true)
    try {
      await data.cancelJob(job.id)
      setConfirm(false)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not cancel this job.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-6 sm:p-8">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold" aria-live="polite">
            {job.status === 'QUEUED' ? 'Your job is in the queue' : 'We’re working on your paper'}
          </h2>
          <p className="mt-1 max-w-md text-sm text-fg-muted">
            {job.status === 'QUEUED'
              ? 'It will start automatically as soon as a slot is free. We can’t predict the exact wait, but most jobs start within a few minutes.'
              : 'This usually takes a few minutes. It keeps running if you close this page — come back any time from your dashboard.'}
          </p>
        </div>
        {job.status === 'QUEUED' && (
          <Button variant="secondary" size="sm" onClick={() => setConfirm(true)}>
            Cancel job
          </Button>
        )}
      </div>
      <div className="mt-8">
        <StageTimeline job={job} />
      </div>
      <p className="mt-8 flex items-center gap-2 border-t border-line pt-5 text-xs text-fg-subtle">
        <Clock className="size-3.5" aria-hidden /> You can safely close this page.
      </p>
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Cancel this job?"
        description="It hasn’t started yet, so nothing will be processed or charged."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={cancel} loading={busy}>
              Cancel job
            </Button>
          </>
        }
      >
        {error && <Alert tone="danger">{error}</Alert>}
      </Dialog>
    </Card>
  )
}

function Completed({ job }: { job: Job }) {
  const tabs = [
    { id: 'overview', label: 'Overview', show: true },
    { id: 'report', label: 'Writing report', show: !!job.analysis },
    { id: 'changes', label: 'Changes', show: !!job.refinement },
    { id: 'formatting', label: 'Formatting', show: !!job.formatting },
  ].filter((t) => t.show)

  return (
    <>
      {job.warnings.length > 0 && (
        <Alert
          tone={job.outcome === 'PARTIAL' ? 'warning' : 'info'}
          title={job.outcome === 'PARTIAL' ? 'Finished — with warnings to review' : 'Your paper is ready. A few things to check:'}
        >
          <ul className="list-disc space-y-1 pl-4">
            {job.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}
      <Tabs defaultValue="overview">
        <TabsList aria-label="Job results">
          {tabs.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview" className="space-y-6">
          <Overview job={job} />
        </TabsContent>
        {job.analysis && (
          <TabsContent value="report" className="space-y-6">
            <ScoreCard before={job.analysis} after={job.analysisAfter} />
            <div>
              <h3 className="mb-3 text-base font-semibold">{job.analysisAfter ? 'Findings in your original draft' : 'Findings'}</h3>
              <FindingsList findings={job.analysis.findings} />
            </div>
          </TabsContent>
        )}
        {job.refinement && (
          <TabsContent value="changes">
            <ChangesPanel refinement={job.refinement} />
          </TabsContent>
        )}
        {job.formatting && (
          <TabsContent value="formatting">
            <FormattingPanel formatting={job.formatting} />
          </TabsContent>
        )}
      </Tabs>
    </>
  )
}

function Overview({ job }: { job: Job }) {
  const highlights: { label: string; value: ReactNode }[] = []
  if (job.analysis && job.analysisAfter)
    highlights.push({ label: 'Estimated AI-likeness', value: <BandChange before={job.analysis.band} after={job.analysisAfter.band} /> })
  else if (job.analysis)
    highlights.push({ label: 'Estimated AI-likeness', value: job.analysis.band.charAt(0) + job.analysis.band.slice(1).toLowerCase() })
  if (job.analysis) highlights.push({ label: 'Findings', value: `${job.analysis.findings.length} writing-pattern findings` })
  if (job.refinement) highlights.push({ label: 'Refined', value: `${job.refinement.refinedBlocks} passages, ${job.refinement.keptOriginal} kept original` })
  if (job.formatting) highlights.push({ label: 'Formatting', value: job.formatting.preset })

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        {highlights.map((h) => (
          <Card key={h.label} className="p-4">
            <p className="text-xs font-medium text-fg-subtle">{h.label}</p>
            <p className="mt-1 text-sm font-semibold">{h.value}</p>
          </Card>
        ))}
      </div>
      <div>
        <h3 className="mb-3 text-base font-semibold">Your files</h3>
        <DownloadList jobId={job.id} outputs={job.outputs} expiresAt={job.expiresAt} />
      </div>
      {job.analysis && (
        <p className="text-xs leading-relaxed text-fg-subtle">
          AI-likeness is an estimate of writing patterns, not proof of authorship. Other detectors may give different results.
        </p>
      )}
    </>
  )
}

function JobDetails({ job }: { job: Job }) {
  const data = useData()
  const navigate = useNavigate()
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const remove = async () => {
    setBusy(true)
    try {
      await data.deleteJob(job.id)
      navigate('/app/history', { replace: true })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Card className="p-5">
        <h2 className="text-sm font-semibold">Quote</h2>
        <dl className="mt-3 space-y-2 text-sm">
          {job.quote.lines.map((l) => (
            <div key={l.label} className="flex justify-between gap-4">
              <dt className="text-fg-muted">{l.label}</dt>
              <dd>{formatUGX(l.amount)}</dd>
            </div>
          ))}
          <div className="flex justify-between gap-4 border-t border-line pt-2 font-semibold">
            <dt>Total</dt>
            <dd>{formatUGX(job.quote.amount)}</dd>
          </div>
        </dl>
        {job.paymentStatus === 'BETA_BYPASS' && <p className="mt-2 text-xs font-medium text-brand-700">Free during beta — you were not charged.</p>}
      </Card>
      <Card className="p-5">
        <h2 className="text-sm font-semibold">Details</h2>
        <dl className="mt-3 space-y-2.5 text-sm">
          <div>
            <dt className="text-xs text-fg-subtle">Paper</dt>
            <dd>
              {job.source.wordCount.toLocaleString('en')} words · ~{job.source.pageEstimate} pages · {job.source.format}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Job ID</dt>
            <dd className="flex items-center gap-2 font-mono text-xs">
              {job.id}
              <button
                className="rounded p-1 text-fg-subtle hover:bg-surface-muted hover:text-fg"
                aria-label="Copy job ID"
                onClick={() => {
                  navigator.clipboard?.writeText(job.id).then(() => setCopied(true), () => undefined)
                }}
              >
                <Copy className="size-3.5" />
              </button>
              {copied && <span className="font-sans text-brand-700">Copied</span>}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Files kept until</dt>
            <dd>{formatDate(job.expiresAt)}</dd>
          </div>
        </dl>
        {isTerminal(job) && (
          <Button variant="ghost" size="sm" className="mt-4 -ml-3 text-red-700 hover:bg-red-50 hover:text-red-800" onClick={() => setConfirm(true)}>
            <Trash2 className="size-4" aria-hidden /> Delete job and files
          </Button>
        )}
      </Card>
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Delete this job?"
        description="Your uploaded paper, results and reports will be permanently deleted. This can't be undone."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={remove} loading={busy}>
              Delete permanently
            </Button>
          </>
        }
      />
    </>
  )
}

function JobSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading job">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-2/3" />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Skeleton className="h-80 rounded-xl" />
        <Skeleton className="h-60 rounded-xl" />
      </div>
    </div>
  )
}
