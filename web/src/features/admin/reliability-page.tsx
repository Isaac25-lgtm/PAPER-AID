import { ArrowLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Select } from '../../components/ui/field'
import { Alert, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'

export interface ServiceReliability {
  service: string
  jobs: number
  completed: number
  partial: number
  failed: number
  cancelled: number
  running: number
  completionRate: number | null
  stops: { code: string; stage: string; count: number }[]
  medianMinutes: number | null
  slowestTenthMinutes: number | null
  costUsd: number
  chargedCredits: number
  refundedCredits: number
  marginCredits: number
  adminRetries: number
}

export interface JobLine {
  id: string
  service: string
  status: string
  outcome: string | null
  failure: string | null
  stage: string | null
  minutes: number | null
  costUsd: number
  chargedCredits: number
  createdAt: string
}

export interface Reliability {
  days: number
  services: ServiceReliability[]
  jobs: JobLine[]
  canaryEnabled: boolean
  /** The daily check's runs, kept out of the figures above. */
  canary: JobLine[]
}

const pct = (v: number | null) => (v === null ? '–' : `${Math.round(v * 100)}%`)
const min = (v: number | null) => (v === null ? '–' : `${v} min`)

/** Reliability by service (owner roadmap 2026-10-03): numbers and codes only, never paper text. */
export function AdminReliabilityPage() {
  useTitle('Reliability')
  const data = useData()
  const [days, setDays] = useState(30)
  const [report, setReport] = useState<Reliability | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setReport(null)
    data.admin
      .reliability(days)
      .then(setReport)
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'Could not load the figures.'))
  }, [data, days])
  return (
    <>
      <Link to="/admin" className="mb-2 -ml-1 inline-flex min-h-10 items-center gap-1.5 px-1 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> Operations
      </Link>
      <PageHeader
        title="Reliability"
        description="Whether jobs finish, where they stop, how long they take, and AI cost against what was charged. Numbers and codes only."
        actions={
          <Select label="Period" value={String(days)} onChange={(e) => setDays(Number(e.target.value))}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </Select>
        }
      />
      {error && <Alert tone="danger">{error}</Alert>}
      {!report && !error && <Skeleton className="h-64 rounded-xl" />}
      {report && report.services.length === 0 && <Alert tone="info">No submitted jobs in this period.</Alert>}
      {report && report.services.length > 0 && (
        <Card className="mb-6 overflow-x-auto p-0">
          <table className="w-full min-w-[60rem] text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-subtle text-left text-fg-muted">
                {['Service', 'Jobs', 'Finished', 'Failed', 'Where they stop', 'Median time', 'Slowest 10%', 'AI cost', 'Charged', 'Refunded', 'Margin'].map(
                  (h) => (
                    <th key={h} className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {report.services.map((s) => (
                <tr key={s.service} className="border-b border-line align-top last:border-0">
                  <td className="px-3 py-2 font-medium text-fg">{s.service}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {s.jobs}
                    {s.running ? <span className="text-fg-subtle"> ({s.running} running)</span> : null}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-20 overflow-hidden rounded-full bg-surface-muted">
                        <div
                          className="h-full bg-brand-600"
                          style={{
                            width: pct(s.completionRate) === '–' ? 0 : pct(s.completionRate),
                          }}
                        />
                      </div>
                      <span className="tabular-nums">{pct(s.completionRate)}</span>
                    </div>
                    {s.partial > 0 && <span className="text-xs text-fg-subtle">{s.partial} with warnings</span>}
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {s.failed}
                    {s.adminRetries ? <span className="text-xs text-fg-subtle"> · {s.adminRetries} retried</span> : null}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {s.stops.length
                      ? s.stops.map((x) => (
                          <div key={x.code + x.stage}>
                            {x.code}
                            {x.stage ? ` at ${x.stage.toLowerCase()}` : ''}: {x.count}
                          </div>
                        ))
                      : '–'}
                  </td>
                  <td className="px-3 py-2 tabular-nums">{min(s.medianMinutes)}</td>
                  <td className="px-3 py-2 tabular-nums">{min(s.slowestTenthMinutes)}</td>
                  <td className="px-3 py-2 tabular-nums">${s.costUsd.toFixed(2)}</td>
                  <td className="px-3 py-2 tabular-nums">{s.chargedCredits.toFixed(1)}</td>
                  <td className="px-3 py-2 tabular-nums">{s.refundedCredits.toFixed(1)}</td>
                  <td className={`px-3 py-2 tabular-nums ${s.marginCredits < 0 ? 'text-red-700' : ''}`}>{s.marginCredits.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-xs text-fg-subtle">
            Charged, refunded and margin are in credits. Margin is charged minus AI cost at each quote's exchange rate; while credits are off, nothing is
            charged.
          </p>
        </Card>
      )}
      {report && (report.canaryEnabled || report.canary.length > 0) && (
        <JobTable
          title="Daily check"
          note={
            report.canaryEnabled
              ? 'A writing check on a fixed paper, run once a day from the check account. Its runs are not counted above.'
              : 'The daily check is off.'
          }
          jobs={report.canary}
        />
      )}
      {report && report.jobs.length > 0 && <JobTable title="Latest jobs" jobs={report.jobs} />}
    </>
  )
}

function JobTable({ title, note, jobs }: { title: string; note?: string; jobs: JobLine[] }) {
  return (
    <Card className="mb-6 overflow-x-auto p-0">
      <p className="px-3 pt-3 text-sm font-semibold">{title}</p>
      {note && <p className="px-3 text-xs text-fg-subtle">{note}</p>}
      {jobs.length === 0 ? (
        <p className="px-3 py-3 text-sm text-fg-muted">No runs in this period.</p>
      ) : (
        <table className="mt-2 w-full min-w-[50rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-fg-muted">
              {['Job', 'Service', 'Status', 'Stopped at', 'Time', 'AI cost', 'Charged'].map((h) => (
                <th key={h} className="px-3 py-1.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-b border-line last:border-0">
                <td className="px-3 py-1.5">
                  <Link to={`/admin/jobs/${j.id}`} className="font-mono text-xs text-brand-700 hover:underline">
                    {j.id}
                  </Link>
                </td>
                <td className="px-3 py-1.5">{j.service}</td>
                <td className="px-3 py-1.5">
                  {j.status.toLowerCase()}
                  {j.outcome === 'PARTIAL' ? ' (warnings)' : ''}
                </td>
                <td className="px-3 py-1.5 text-xs">{j.failure ? `${j.failure}${j.stage ? ` at ${j.stage.toLowerCase()}` : ''}` : '–'}</td>
                <td className="px-3 py-1.5 tabular-nums">{min(j.minutes)}</td>
                <td className="px-3 py-1.5 tabular-nums">${j.costUsd.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{j.chargedCredits.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}
