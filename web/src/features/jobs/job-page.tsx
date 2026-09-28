import { ArrowLeft, CircleSlash, Clock, Copy, FileSearch, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Dialog, Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/overlays'
import { Alert, Card, EmptyState, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate, formatDateTime, formatTokens } from '../../lib/format'
import type { Job, Quote } from '../../lib/types'
import { STYLE_OPTIONS } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import { BandChange, DownloadList, FormattingPanel, LatexPanel, SourceCheckPanel } from '../results/report'
import { Workspace } from '../results/workspace'
import { ProposalReviewPanel } from '../proposals/review-panel'
import { useJob } from './hooks'
import { jobLink, jobTitle, serviceNames, StageTimeline, StatusBadge } from './job-bits'

const isTerminal = (j: Job) => j.status === 'COMPLETED' || j.status === 'FAILED' || j.status === 'CANCELLED'

export function JobPage() {
  const { jobId = '' } = useParams()
  const { job, loading, blocked } = useJob(jobId)
  useTitle(job ? jobTitle(job) : 'Job')

  if (loading) return <JobSkeleton />
  if (blocked)
    return (
      <Alert
        tone="warning"
        title="We couldn't load this job"
        action={
          <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
            Refresh the page
          </Button>
        }
      >
        {blocked}
      </Alert>
    )
  if (!job)
    return (
      <EmptyState icon={<FileSearch className="size-5" />} title="We couldn't find this job" action={<ButtonLink to="/app">Back to dashboard</ButtonLink>}>
        It may have been deleted, or the link may be wrong.
      </EmptyState>
    )
  if (job.status === 'DRAFT' || job.status === 'QUOTED') return <Navigate to={jobLink(job)} replace /> // not submitted yet: resume it

  return (
    <>
      <Link to="/app/history" className="mb-2 -ml-1 inline-flex min-h-10 items-center gap-1.5 px-1 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> All jobs
      </Link>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-bold break-words sm:text-2xl">{jobTitle(job)}</h1>
          <p className="mt-1 text-sm text-fg-muted">
            {serviceNames(job)} · Submitted {formatDateTime(job.createdAt)}
          </p>
        </div>
        <div className="shrink-0 self-start">
          <StatusBadge job={job} />
        </div>
      </div>

      {job.status === 'COMPLETED' && job.analysis ? (
        // The review workspace needs the full width; the job's details follow it.
        <div className="space-y-6">
          <JobBody job={job} />
          <div className="grid gap-4 md:grid-cols-2">
            <JobDetails job={job} />
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
          <div className="min-w-0 space-y-6">
            <JobBody job={job} />
          </div>
          <aside className="space-y-4">
            <JobDetails job={job} />
          </aside>
        </div>
      )}
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
          Nothing was charged: your tokens, including any estimate, went back to your balance.{' '}
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
          <p className="text-sm text-fg-muted">Nothing was processed, and any tokens held for it went back to your balance.</p>
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
    { id: 'paper', label: 'Your paper', show: !!job.analysis },
    { id: 'overview', label: 'Overview', show: !job.analysis },
    { id: 'sources', label: 'Source check', show: !!job.research },
    { id: 'formatting', label: 'Formatting', show: !!job.formatting },
    { id: 'latex', label: 'LaTeX', show: !!job.latex },
    { id: 'proposal', label: 'Proposal review', show: !!job.proposalReview },
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
      <Tabs defaultValue={job.analysis ? 'paper' : 'overview'}>
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
          <TabsContent value="paper">
            <Workspace job={job} />
          </TabsContent>
        )}
        {job.research && (
          <TabsContent value="sources">
            <SourceCheckPanel research={job.research} />
          </TabsContent>
        )}
        {job.formatting && (
          <TabsContent value="formatting">
            <FormattingPanel formatting={job.formatting} />
          </TabsContent>
        )}
        {job.latex && (
          <TabsContent value="latex">
            <LatexPanel latex={job.latex} />
          </TabsContent>
        )}
        {job.proposalReview && (
          <TabsContent value="proposal">
            <ProposalReviewPanel review={job.proposalReview} />
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
  if (job.proposalReview) {
    const open = job.proposalReview.items.filter((i) => i.status === 'MISSING' || i.status === 'NEEDS_REVIEW').length
    highlights.push({ label: 'Proposal review', value: `${open} of ${job.proposalReview.items.length} checks need attention` })
  }

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
      {job.quote && (
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Quote</h2>
          <dl className="mt-3 space-y-2 text-sm">
            {job.quote.lines.map((l) => (
              <div key={l.label} className="flex justify-between gap-4">
                <dt className="text-fg-muted">{l.label}</dt>
                <dd>{formatTokens(l.amount)}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-4 border-t border-line pt-2 font-semibold">
              <dt>Most it could cost</dt>
              <dd>{formatTokens(job.quote.amount)}</dd>
            </div>
          </dl>
          <BillingNote job={job} quote={job.quote} />
        </Card>
      )}
      <Card className="p-5">
        <h2 className="text-sm font-semibold">Details</h2>
        <dl className="mt-3 space-y-2.5 text-sm">
          {(job.selection.writing === 'REFINE' || job.selection.writing === 'REDRAFT') && (
            <div>
              <dt className="text-xs text-fg-subtle">Writing style</dt>
              <dd>
                {STYLE_OPTIONS.find((s) => s.id === job.selection.style)?.title} ·{' '}
                {job.selection.writing === 'REDRAFT' ? 'deep redraft' : `${job.selection.intensity === 'LIGHT' ? 'light' : 'standard'} refinement`}
              </dd>
            </div>
          )}
          {job.source && (
            <div>
              <dt className="text-xs text-fg-subtle">Paper</dt>
              <dd>
                {job.source.wordCount.toLocaleString('en')} words · ~{job.source.pageEstimate} pages · {job.source.format}
              </dd>
            </div>
          )}
          <div>
            <dt className="text-xs text-fg-subtle">Job ID</dt>
            <dd className="flex items-center gap-2 font-mono text-xs">
              {job.id}
              <button
                className="-my-2 grid size-10 place-items-center rounded text-fg-subtle hover:bg-surface-muted hover:text-fg"
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

/** Where this job's credits stand: held while it runs, then what was charged and what came back. */
function BillingNote({ job, quote }: { job: Job; quote: Quote }) {
  const b = job.billing
  const paid = b.feePaid + b.charged
  if (b.state === 'HELD')
    return <p className="mt-3 rounded-lg bg-surface-subtle p-2.5 text-xs text-fg-muted">{formatTokens(b.held)} is held while your job runs. You&rsquo;re charged only for the work done; the rest comes back.</p>
  if (b.state === 'SETTLED')
    return (
      <p className="mt-3 rounded-lg bg-brand-50 p-2.5 text-xs font-medium text-brand-800">
        Charged {formatTokens(paid)}{b.feePaid > 0 && ` (including the ${formatTokens(b.feePaid)} estimate)`}. {quote.amount - paid > 0 && `${formatTokens(quote.amount - paid)} less than the most it could cost.`}
      </p>
    )
  if (b.state === 'NONE' && job.paymentStatus === 'NOT_REQUIRED')
    return <p className="mt-3 rounded-lg bg-brand-50 p-2.5 text-xs font-medium text-brand-800">Not charged: PaperAid is in testing.</p>
  if (b.state === 'RELEASED' || b.refunded > 0)
    return <p className="mt-3 rounded-lg bg-surface-subtle p-2.5 text-xs text-fg-muted">Nothing was charged for this job{b.refunded > 0 && `, and the ${formatTokens(b.refunded)} estimate was refunded`}.</p>
  return null
}
