import { clsx } from 'clsx'
import { ArrowLeft, Copy, Search, Wallet as WalletIcon } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Input, Select } from '../../components/ui/field'
import { Dialog } from '../../components/ui/overlays'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData, type JobQuery } from '../../lib/data'
import { formatDateTime, formatDuration, formatNumber, formatRelative, formatUGX } from '../../lib/format'
import { SERVICES, SERVICE_ORDER, STAGE_LABELS, STATUS_LABELS } from '../../lib/services'
import type { AdminJob, AdminSummary, JobStatus, ServiceId, WalletSummary } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { walletChanged } from '../../lib/use-wallet'
import { serviceNames, StatusBadge } from '../jobs/job-bits'

const usd = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'danger' }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-fg-subtle">{label}</p>
      <p className={clsx('mt-1 text-2xl font-bold tracking-tight', tone === 'danger' ? 'text-red-600' : 'text-fg')}>{value}</p>
    </Card>
  )
}

export function AdminOverviewPage() {
  useTitle('Admin')
  const data = useData()
  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [rows, setRows] = useState<AdminJob[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<JobStatus | 'ALL'>('ALL')
  const [service, setService] = useState<ServiceId | 'ALL'>('ALL')
  const [search, setSearch] = useState('')
  const [confirmSwitch, setConfirmSwitch] = useState(false)
  const [switching, setSwitching] = useState(false)

  const refreshSummary = useCallback(() => data.admin.summary().then(setSummary), [data])
  useEffect(() => {
    refreshSummary()
  }, [refreshSummary])

  const toggleProcessing = async () => {
    if (!summary) return
    setSwitching(true)
    await data.admin.setProcessing(!summary.processingEnabled)
    await refreshSummary()
    setSwitching(false)
    setConfirmSwitch(false)
  }

  const load = useCallback(
    async (query: JobQuery, append: boolean) => {
      setLoading(true)
      const page = await data.admin.listJobs({ ...query, limit: 12 })
      setRows((prev) => (append ? [...prev, ...page.items] : page.items))
      setCursor(page.nextCursor)
      setLoading(false)
    },
    [data],
  )

  useEffect(() => {
    const t = setTimeout(() => load({ status, service, search: search.trim() }, false), 200)
    return () => clearTimeout(t)
  }, [load, status, service, search])

  return (
    <>
      <PageHeader
        title="Operations"
        description="What's queued, what failed, and what it cost. Paper content is never shown here."
        actions={
          summary && (
            <div className="flex gap-2">
              <ButtonLink to="/admin/credits" variant="secondary" size="sm">
                <WalletIcon className="size-4" aria-hidden /> Credits
              </ButtonLink>
              <Button variant={summary.processingEnabled ? 'secondary' : 'primary'} size="sm" onClick={() => setConfirmSwitch(true)}>
                {summary.processingEnabled ? 'Pause processing' : 'Resume processing'}
              </Button>
            </div>
          )
        }
      />
      {summary && !summary.processingEnabled && (
        <Alert tone="warning" className="mb-4" title="Processing is paused">
          New and queued jobs wait until processing resumes. Nothing is lost.
        </Alert>
      )}
      <Dialog
        open={confirmSwitch}
        onOpenChange={setConfirmSwitch}
        title={summary?.processingEnabled ? 'Pause all processing?' : 'Resume processing?'}
        description={
          summary?.processingEnabled
            ? 'No new model work will start. Queued jobs stay queued and students can still submit. Jobs mid-stage finish that stage.'
            : 'Queued jobs will start again within a minute.'
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmSwitch(false)}>
              Back
            </Button>
            <Button variant={summary?.processingEnabled ? 'danger' : 'primary'} loading={switching} onClick={toggleProcessing}>
              {summary?.processingEnabled ? 'Pause processing' : 'Resume processing'}
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {summary ? (
          <>
            <Tile label="Jobs (24h)" value={formatNumber(summary.jobs24h)} />
            <Tile label="Processing" value={String(summary.active)} />
            <Tile label="Queued" value={String(summary.queued)} />
            <Tile label="Completion rate" value={`${Math.round(summary.completionRate * 100)}%`} />
            <Tile label="Failures (24h)" value={String(summary.failures24h)} tone={summary.failures24h ? 'danger' : undefined} />
            <Tile label="AI spend (24h)" value={usd(summary.spend24hUsd)} />
          </>
        ) : (
          Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)
        )}
      </div>

      <Card className="mt-6">
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-[1fr_11rem_13rem]">
          <div className="relative">
            <Input label="Search" placeholder="Job ID, email or file name" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Search className="pointer-events-none absolute right-3 bottom-3 size-4 text-fg-subtle" aria-hidden />
          </div>
          <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value as JobStatus | 'ALL')}>
            <option value="ALL">All statuses</option>
            {(['QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED'] as JobStatus[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
          <Select label="Service" value={service} onChange={(e) => setService(e.target.value as ServiceId | 'ALL')}>
            <option value="ALL">All services</option>
            {SERVICE_ORDER.map((s) => (
              <option key={s} value={s}>
                {SERVICES[s].name}
              </option>
            ))}
          </Select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[46rem] text-sm">
            <caption className="sr-only">Jobs</caption>
            <thead className="bg-surface-subtle text-left text-xs text-fg-subtle">
              <tr>
                <th className="px-4 py-2.5 font-medium">Job</th>
                <th className="px-4 py-2.5 font-medium">User</th>
                <th className="px-4 py-2.5 font-medium">Service</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 text-right font-medium">Duration</th>
                <th className="px-4 py-2.5 text-right font-medium">AI cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => (
                <tr key={r.job.id} className="hover:bg-surface-subtle">
                  <td className="px-4 py-3">
                    <Link to={`/admin/jobs/${r.job.id}`} className="font-mono text-xs font-medium text-brand-700 hover:underline">
                      {r.job.id}
                    </Link>
                  </td>
                  <td className="max-w-48 truncate px-4 py-3 text-fg-muted">{r.ownerEmail}</td>
                  <td className="px-4 py-3">{serviceNames(r.job)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge job={r.job} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-fg-muted">{formatRelative(r.job.createdAt)}</td>
                  <td className="px-4 py-3 text-right text-fg-muted">{r.durationSec ? formatDuration(r.durationSec) : '—'}</td>
                  <td className="px-4 py-3 text-right font-medium">{usd(r.costUsd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && rows.length === 0 && <p className="p-6 text-center text-sm text-fg-muted">No jobs match these filters.</p>}
        {loading && rows.length === 0 && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-8" />
            ))}
          </div>
        )}
        {cursor && (
          <div className="border-t border-line p-3 text-center">
            <Button variant="ghost" size="sm" loading={loading} onClick={() => load({ status, service, search: search.trim(), cursor }, true)}>
              Load more
            </Button>
          </div>
        )}
      </Card>
    </>
  )
}

export function AdminJobPage() {
  const { jobId = '' } = useParams()
  useTitle(`Admin · ${jobId}`)
  const data = useData()
  const [detail, setDetail] = useState<AdminJob | null | undefined>(undefined)
  const [action, setAction] = useState<'retry' | 'cancel' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(() => data.admin.getJob(jobId).then(setDetail), [data, jobId])
  useEffect(() => {
    refresh()
  }, [refresh])

  if (detail === undefined) return <Skeleton className="h-96 rounded-xl" />
  if (detail === null) return <EmptyState icon={<Search className="size-5" />} title="Job not found">No job has this ID.</EmptyState>

  const { job } = detail
  const logFilter = `jsonPayload.jobId="${job.id}"`
  const run = async () => {
    if (!action) return
    setBusy(true)
    setError(null)
    try {
      await (action === 'retry' ? data.admin.retryJob(job.id) : data.admin.cancelJob(job.id))
      setAction(null)
      await refresh()
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Link to="/admin" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> Operations
      </Link>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-mono text-xl font-bold">{job.id}</h1>
          <p className="mt-1 text-sm text-fg-muted">
            {detail.ownerEmail} · {serviceNames(job)} · {job.source.wordCount.toLocaleString('en')} words
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge job={job} />
          {job.status === 'FAILED' && job.failure?.retryable && (
            <Button size="sm" onClick={() => setAction('retry')}>
              Retry job
            </Button>
          )}
          {job.status === 'QUEUED' && (
            <Button size="sm" variant="secondary" onClick={() => setAction('cancel')}>
              Cancel job
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-6">
          {job.failure && (
            <Alert tone="danger" title={`Failure: ${job.failure.code}${job.failure.retryable ? ' (retryable)' : ' (final)'}`}>
              <p>User saw: “{job.failure.userMessage}”</p>
              {detail.failureDetail && <p className="mt-1 font-mono text-xs break-all opacity-80">{detail.failureDetail}</p>}
            </Alert>
          )}
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Model calls</h2>
            {detail.modelCalls.length === 0 ? (
              <p className="mt-2 text-sm text-fg-muted">No paid model calls for this job.</p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[40rem] text-xs">
                  <thead className="text-left text-fg-subtle">
                    <tr>
                      <th className="py-2 pr-3 font-medium">Stage</th>
                      <th className="py-2 pr-3 font-medium">Model</th>
                      <th className="py-2 pr-3 font-medium">Prompt</th>
                      <th className="py-2 pr-3 text-right font-medium">In / cached / out</th>
                      <th className="py-2 pr-3 text-right font-medium">Latency</th>
                      <th className="py-2 text-right font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {detail.modelCalls.map((c, i) => (
                      <tr key={i}>
                        <td className="py-2 pr-3">{STAGE_LABELS[c.stage]}</td>
                        <td className="py-2 pr-3 font-mono">
                          {c.provider}/{c.model}
                        </td>
                        <td className="py-2 pr-3 font-mono">{c.promptVersion}</td>
                        <td className="py-2 pr-3 text-right">
                          {formatNumber(c.inputTokens)} / {formatNumber(c.cachedTokens)} / {formatNumber(c.outputTokens)}
                        </td>
                        <td className="py-2 pr-3 text-right">{(c.latencyMs / 1000).toFixed(1)}s</td>
                        <td className="py-2 text-right font-medium">{usd(c.costUsd)}</td>
                      </tr>
                    ))}
                    <tr className="font-semibold">
                      <td className="py-2" colSpan={5}>
                        Job total
                      </td>
                      <td className="py-2 text-right">{usd(detail.costUsd)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Timeline</h2>
            <ol className="mt-3 space-y-2.5 border-l-2 border-line pl-4">
              {detail.events.map((e) => (
                <li key={e.label + e.at} className="text-sm">
                  <span className="font-medium">{e.label}</span>
                  <span className="ml-2 text-xs text-fg-subtle">{formatDateTime(e.at)}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
        <aside className="space-y-4">
          <Card className="p-5 text-sm">
            <h2 className="font-semibold">Quote &amp; payment</h2>
            <p className="mt-2 text-fg-muted">
              {formatUGX(job.quote.amount)} · pricing {job.quote.pricingVersion}
            </p>
            <p className="text-fg-muted">Payment: {job.paymentStatus.replace('_', ' ').toLowerCase()}</p>
          </Card>
          <Card className="p-5 text-sm">
            <h2 className="font-semibold">Files</h2>
            <p className="mt-2 break-words text-fg-muted">{job.source.name}</p>
            <p className="text-xs text-fg-subtle">
              {job.source.format} · {job.outputs.length} output files · paper content hidden
            </p>
          </Card>
          <Card className="p-5 text-sm">
            <h2 className="font-semibold">Trace in Cloud Logging</h2>
            <code className="mt-2 block rounded-md bg-surface-muted p-2 font-mono text-xs break-all">{logFilter}</code>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 -ml-3"
              onClick={() => navigator.clipboard?.writeText(logFilter).then(() => setCopied(true), () => undefined)}
            >
              <Copy className="size-3.5" aria-hidden /> {copied ? 'Copied' : 'Copy filter'}
            </Button>
          </Card>
          <Card className="p-5 text-sm">
            <h2 className="font-semibold">Admin actions</h2>
            {detail.adminActions.length === 0 ? (
              <p className="mt-2 text-fg-muted">None.</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {detail.adminActions.map((a) => (
                  <li key={a.at} className="text-fg-muted">
                    <span className="font-medium text-fg">{a.action}</span> by {a.actor} · {formatRelative(a.at)}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>

      <Dialog
        open={action !== null}
        onOpenChange={(open) => !open && setAction(null)}
        title={action === 'retry' ? 'Retry this job?' : 'Cancel this job?'}
        description={
          action === 'retry'
            ? 'It will be queued again from its last completed stage. Spend so far counts against the same budget.'
            : 'The user will see this job as cancelled. Nothing further will be processed.'
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)}>
              Back
            </Button>
            <Button variant={action === 'cancel' ? 'danger' : 'primary'} loading={busy} onClick={run}>
              {action === 'retry' ? 'Retry job' : 'Cancel job'}
            </Button>
          </>
        }
      >
        {error && <Alert tone="danger">{error}</Alert>}
      </Dialog>
    </>
  )
}

export function AdminCreditsPage() {
  useTitle('Credits · Admin')
  const data = useData()
  const [wallets, setWallets] = useState<WalletSummary[] | null>(null)
  const [search, setSearch] = useState('')
  const [email, setEmail] = useState('')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const load = useCallback((term: string) => data.admin.listWallets(term).then(setWallets), [data])
  useEffect(() => {
    const t = setTimeout(() => load(search.trim()), 200)
    return () => clearTimeout(t)
  }, [load, search])

  const grant = async (event: FormEvent) => {
    event.preventDefault()
    const value = Number(amount)
    if (!Number.isInteger(value) || value <= 0) return setResult({ tone: 'danger', text: 'Enter a whole number of UGX above zero.' })
    setBusy(true)
    setResult(null)
    try {
      const updated = await data.admin.grantCredits(email.trim(), value, note)
      setResult({ tone: 'success', text: `Added ${formatUGX(value)} to ${updated.email}. Their balance is now ${formatUGX(updated.available)}.` })
      walletChanged() // the admin may have credited their own account
      setAmount('')
      setNote('')
      await load(search.trim())
    } catch (e) {
      setResult({ tone: 'danger', text: e instanceof DataError ? e.message : 'The credits could not be added.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Link to="/admin" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> Operations
      </Link>
      <PageHeader title="Credits" description="Add credits to a student's balance: test credits while payments are not live, refunds or goodwill later." />
      <div className="grid items-start gap-6 lg:grid-cols-[22rem_1fr]">
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Add credits</h2>
          <form className="mt-4 space-y-4" onSubmit={grant}>
            <Input label="Student email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} hint="They must have signed in once." />
            <Input label="Amount (UGX)" inputMode="numeric" required value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9]/g, ''))} />
            <Input label="Note (optional)" value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} hint="Shown in the student's credit history." />
            {result && <Alert tone={result.tone}>{result.text}</Alert>}
            <Button type="submit" className="w-full" loading={busy}>
              Add credits
            </Button>
          </form>
        </Card>
        <Card className="overflow-hidden">
          <div className="border-b border-line p-4">
            <Input label="Find a student" placeholder="Email" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {wallets === null ? (
            <Skeleton className="m-4 h-24" />
          ) : wallets.length === 0 ? (
            <p className="p-4 text-sm text-fg-muted">No matching students have opened their credits yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-subtle text-left text-xs text-fg-subtle">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Student</th>
                  <th className="px-4 py-2.5 text-right font-medium">Available</th>
                  <th className="px-4 py-2.5 text-right font-medium">Held</th>
                  <th className="hidden px-4 py-2.5 text-right font-medium sm:table-cell">Last activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {wallets.map((w) => (
                  <tr key={w.email} className="cursor-pointer hover:bg-surface-subtle" onClick={() => setEmail(w.email)}>
                    <td className="px-4 py-2.5">{w.email}</td>
                    <td className="px-4 py-2.5 text-right font-medium">{formatUGX(w.available)}</td>
                    <td className="px-4 py-2.5 text-right text-fg-muted">{formatUGX(w.held)}</td>
                    <td className="hidden px-4 py-2.5 text-right text-fg-subtle sm:table-cell">{formatRelative(w.updatedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  )
}
