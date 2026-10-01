import { Inbox, SearchX } from 'lucide-react'
import { useState } from 'react'
import { Button, ButtonLink } from '../../components/ui/button'
import { Select } from '../../components/ui/field'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { SERVICES, SERVICE_ORDER, STATUS_LABELS } from '../../lib/services'
import type { JobStatus, ServiceId } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useJobList } from './hooks'
import { JobRow } from './job-bits'

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

export { DashboardPage, YourWorkPage } from './your-work'

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
          <EmptyState icon={<Inbox className="size-5" />} title="No papers yet" action={<ButtonLink to="/app/new">Start a job</ButtonLink>}>
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

