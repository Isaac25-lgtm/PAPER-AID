import { ChartColumn, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input, TextArea } from '../../components/ui/field'
import { Alert, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import type { DataProject } from '../../lib/datalab-types'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { INVITE_ONLY_REASON, NOT_CONFIGURED_REASON } from '../../lib/services'
import { useTitle } from '../../lib/use-title'

/** Data Lab (owner decision 2026-10-03): the researcher's analysis projects, and a new one. */
export function DataLabPage() {
  useTitle('Data Lab')
  const data = useData()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<DataProject[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const availability = data.config.availability.DATALAB

  useEffect(() => {
    data.datalab
      .list()
      .then(setProjects)
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load your projects.'))
  }, [data])

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const p = await data.datalab.create(title.trim() || 'My analysis', purpose.trim())
      navigate(`/app/datalab/${p.id}`)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start this project.')
    } finally {
      setBusy(false)
    }
  }

  const reason = availability === 'invite_only' ? INVITE_ONLY_REASON : availability === 'not_configured' ? NOT_CONFIGURED_REASON : availability !== 'available' ? 'Data Lab is coming soon.' : null
  return (
    <>
      <PageHeader
        title="Data Lab"
        description="Upload a dataset. PaperAid checks it, runs the analyses you choose and writes them up, every number calculated by code."
        actions={!reason && !creating ? <Button size="sm" onClick={() => setCreating(true)}><Plus className="size-4" aria-hidden /> New analysis</Button> : undefined}
      />
      {reason && <Alert tone="info" className="mb-5">{reason}</Alert>}
      {error && <Alert tone="danger" className="mb-5">{error}</Alert>}
      {creating && (
        <Card className="mb-6 space-y-4 p-5 sm:p-6">
          <Input label="Name of this analysis" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Malaria cases by district, 2024" />
          <TextArea label="What do you want to find out? (optional)" rows={3} maxLength={1500} value={purpose} onChange={(e) => setPurpose(e.target.value)}
            hint="It helps the report focus on your question. You upload the data next." />
          <div className="flex gap-2">
            <Button loading={busy} onClick={create}>Continue</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setCreating(false)}>Cancel</Button>
          </div>
        </Card>
      )}
      {projects === null && !error ? (
        <Skeleton className="h-24 rounded-2xl" />
      ) : projects && projects.length === 0 && !creating ? (
        <EmptyState icon={<ChartColumn className="size-6" aria-hidden />} title="No analyses yet"
          action={!reason && <Button onClick={() => setCreating(true)}><Plus className="size-4" aria-hidden /> New analysis</Button>}>
          Upload a CSV or Excel file. PaperAid shows what is in it, asks before changing anything, and runs the analyses you choose.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {projects?.map((p) => (
            <li key={p.id}>
              <Link to={`/app/datalab/${p.id}`} className="block rounded-2xl border border-line bg-white p-5 shadow-card transition-colors hover:border-brand-300">
                <p className="font-semibold text-fg">{p.title}</p>
                <p className="mt-1 text-sm text-fg-muted">
                  {p.source ? `${p.source.name} · ${p.rows.toLocaleString()} records · ${p.analyses.length} analys${p.analyses.length === 1 ? 'is' : 'es'}` : 'No data yet'}
                  {p.reports.length > 0 && ' · report written'}
                </p>
                <p className="mt-1 text-xs text-fg-subtle">Kept until {formatDate(p.expiresAt)} unless you work on it again.</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
