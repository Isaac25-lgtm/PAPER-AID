import { ArrowRight, FileUp, Inbox, Loader2, SearchX } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Select } from '../../components/ui/field'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { SERVICES, SERVICE_ORDER, STATUS_LABELS } from '../../lib/services'
import type { Job, JobStatus, ServiceId } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useAuth } from '../auth/auth-context'
import { useJobList } from './hooks'
import { JobRow } from './job-bits'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 p-2">
          <Skeleton className="size-10 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      ))}
    </div>
  )
}

function ActiveJobCard({ jobs }: { jobs: Job[] }) {
  const active = jobs.filter((j) => j.status === 'QUEUED' || j.status === 'PROCESSING')
  return (
    <Card className="flex flex-col p-5 sm:p-6">
      <h2 className="text-sm font-semibold">In progress</h2>
      {active.length === 0 ? (
        <p className="mt-2 flex-1 text-sm text-fg-muted">Nothing running right now. Jobs keep going if you close the page.</p>
      ) : (
        <ul className="mt-3 flex-1 space-y-4">
          {active.slice(0, 2).map((job) => (
            <li key={job.id}>
              <Link to={`/app/jobs/${job.id}`} className="group block">
                <p className="truncate text-sm font-medium group-hover:text-brand-700">{job.source.name}</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-xs text-fg-subtle">
                  <Loader2 className="size-3 animate-spin text-brand-600" aria-hidden />
                  {job.status === 'QUEUED' ? 'Waiting to start' : 'Processing'}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function DashboardPage() {
  useTitle('Dashboard')
  const { user } = useAuth()
  const { jobs, loading, error } = useJobList({ limit: 6 })
  const firstName = user?.displayName.split(' ')[0] ?? ''

  return (
    <>
      <PageHeader title={`${greeting()}, ${firstName}`} description="Upload a paper or pick up where you left off." />

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Link
          to="/app/new"
          className="group relative overflow-hidden rounded-2xl bg-brand-700 p-6 text-white shadow-raised transition-colors hover:bg-brand-800 sm:p-8"
        >
          <div aria-hidden className="absolute -top-16 -right-10 size-56 rounded-full bg-brand-500/40 blur-2xl" />
          <div className="relative flex items-start gap-5">
            <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-white/15 ring-1 ring-white/20">
              <FileUp className="size-6" aria-hidden />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">New paper job</h2>
              <p className="mt-1 max-w-md text-sm text-brand-100">Upload a Word file or PDF, choose what you need, and see your price before you start.</p>
              <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold">
                Upload your paper <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
              </span>
            </div>
          </div>
        </Link>
        {loading ? <Skeleton className="h-full min-h-32 rounded-xl" /> : <ActiveJobCard jobs={jobs} />}
      </div>

      <section className="mt-10" aria-labelledby="recent-title">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="recent-title" className="text-lg font-semibold">
            Recent jobs
          </h2>
          {jobs.length > 0 && (
            <Link to="/app/history" className="-mr-2 inline-flex min-h-10 items-center px-2 text-sm font-semibold text-brand-700 hover:underline">
              View all
            </Link>
          )}
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        {loading ? (
          <Card>
            <ListSkeleton />
          </Card>
        ) : jobs.length === 0 ? (
          <EmptyState icon={<Inbox className="size-5" />} title="No papers yet" action={<ButtonLink to="/app/new">Upload your first paper</ButtonLink>}>
            Upload a paper, choose a service and see your price. Your finished files will appear here.
          </EmptyState>
        ) : (
          <Card className="p-1.5">
            <ul className="divide-y divide-line">
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </ul>
          </Card>
        )}
      </section>
    </>
  )
}

export function HistoryPage() {
  useTitle('History')
  const [status, setStatus] = useState<JobStatus | 'ALL'>('ALL')
  const [service, setService] = useState<ServiceId | 'ALL'>('ALL')
  const { jobs, loading, loadingMore, error, hasMore, loadMore } = useJobList({ status, service, limit: 10 })
  const filtered = status !== 'ALL' || service !== 'ALL'

  return (
    <>
      <PageHeader title="History" description="Every paper job on your account. Files are kept for 30 days." />
      <div className="mb-4 grid gap-3 sm:grid-cols-[12rem_14rem]">
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
      {error && <Alert tone="danger">{error}</Alert>}
      {loading ? (
        <Card>
          <ListSkeleton rows={6} />
        </Card>
      ) : jobs.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={<SearchX className="size-5" />}
            title="No jobs match these filters"
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setStatus('ALL')
                  setService('ALL')
                }}
              >
                Clear filters
              </Button>
            }
          >
            Try a different status or service.
          </EmptyState>
        ) : (
          <EmptyState icon={<Inbox className="size-5" />} title="No papers yet" action={<ButtonLink to="/app/new">Upload a paper</ButtonLink>}>
            Your paper jobs will be listed here.
          </EmptyState>
        )
      ) : (
        <>
          <Card className="p-1.5">
            <ul className="divide-y divide-line">
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </ul>
          </Card>
          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </>
  )
}

