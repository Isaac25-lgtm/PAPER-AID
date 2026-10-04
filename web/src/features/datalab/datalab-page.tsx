import { ChartColumn, MessageSquareQuote, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input, TextArea } from '../../components/ui/field'
import { Alert, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import type { DataProject } from '../../lib/datalab-types'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { INVITE_ONLY_REASON, NOT_CONFIGURED_REASON } from '../../lib/services'
import { useTitle } from '../../lib/use-title'

type Kind = 'QUANT' | 'QUAL'

const KINDS: { kind: Kind; title: string; icon: typeof ChartColumn; body: string; analyses: string[]; placeholder: string; question: string }[] = [
  {
    kind: 'QUANT', title: 'Quantitative data', icon: ChartColumn, body: 'A dataset of numbers and categories, such as a survey or records, as CSV or Excel.',
    analyses: ['Describe a variable', 'Compare two groups', 'Relate two categories', 'Correlate two numbers', 'Map by district, subcounty, sub-region or region',
      'Filter by any variable', 'Analysis report and Excel workbook'],
    placeholder: 'e.g. Malaria cases by district, 2024', question: 'What do you want to find out?',
  },
  {
    kind: 'QUAL', title: 'Qualitative data', icon: MessageSquareQuote, body: 'Interviews, focus groups or open answers, as text, Word or PDF.',
    analyses: ['Codes with quotes, each checked word for word', 'Themes that answer your question', 'Analysis report and a codebook in Excel'],
    placeholder: 'e.g. Reaching care in Kamuli: mothers’ interviews', question: 'Your research question',
  },
]

/** Data Lab (owner decisions 2026-10-03/04): quantitative and qualitative analysis, each with its projects. */
export function DataLabPage() {
  useTitle('Data Lab')
  const data = useData()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const asked = params.get('new')
  const [projects, setProjects] = useState<DataProject[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState<Kind | null>(asked === 'QUAL' ? 'QUAL' : asked === 'QUANT' || asked === 'MAP' ? 'QUANT' : null)
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

  const create = async (kind: Kind) => {
    setBusy(true)
    setError(null)
    try {
      const p = await data.datalab.create(title.trim() || (kind === 'QUAL' ? 'My interviews' : 'My analysis'), purpose.trim(), kind)
      navigate(`/app/datalab/${p.id}${asked === 'MAP' ? '?map=1' : ''}`)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start this project.')
    } finally {
      setBusy(false)
    }
  }

  const reason = availability === 'invite_only' ? INVITE_ONLY_REASON : availability === 'not_configured' ? NOT_CONFIGURED_REASON : availability !== 'available' ? 'Data Lab is coming soon.' : null
  return (
    <>
      <PageHeader title="Data Lab" description="Analyse your data, every number calculated by code. Choose the kind of data you have." />
      {reason && <Alert tone="info" className="mb-5">{reason}</Alert>}
      {error && <Alert tone="danger" className="mb-5">{error}</Alert>}
      <div className="grid gap-5 lg:grid-cols-2">
        {KINDS.map((k) => {
          const mine = projects?.filter((p) => (p.kind ?? 'QUANT') === k.kind) ?? []
          return (
            <section key={k.kind} aria-labelledby={`kind-${k.kind}`} className="space-y-3">
              <Card className="space-y-3 p-5 sm:p-6">
                <div className="flex items-start gap-3">
                  <span className="rounded-xl bg-brand-50 p-2 text-brand-700"><k.icon className="size-5" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <h2 id={`kind-${k.kind}`} className="text-lg font-semibold">{k.title}</h2>
                    <p className="text-sm text-fg-muted">{k.body}</p>
                  </div>
                </div>
                <ul className="flex flex-wrap gap-1.5">
                  {k.analyses.map((a) => <li key={a} className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs text-fg-muted">{a}</li>)}
                </ul>
                {creating === k.kind ? (
                  <div className="space-y-3 border-t border-line pt-3">
                    <Input label="Name of this analysis" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={k.placeholder} />
                    <TextArea label={`${k.question} (optional)`} rows={2} maxLength={1500} value={purpose} onChange={(e) => setPurpose(e.target.value)}
                      hint={k.kind === 'QUAL' ? 'The themes answer it. You add the transcripts next.' : 'It helps the report focus on your question. You upload the data next.'} />
                    <div className="flex gap-2">
                      <Button loading={busy} onClick={() => void create(k.kind)}>Continue</Button>
                      <Button variant="secondary" disabled={busy} onClick={() => setCreating(null)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  !reason && <Button size="sm" onClick={() => { setCreating(k.kind); setTitle(''); setPurpose('') }}><Plus className="size-4" aria-hidden /> New {k.kind === 'QUAL' ? 'qualitative' : 'quantitative'} analysis</Button>
                )}
              </Card>
              {projects === null && !error ? (
                <Skeleton className="h-20 rounded-2xl" />
              ) : (
                <ul className="space-y-2">
                  {mine.map((p) => (
                    <li key={p.id}>
                      <Link to={`/app/datalab/${p.id}`} className="block rounded-2xl border border-line bg-white p-4 shadow-card transition-colors hover:border-brand-300">
                        <p className="font-semibold text-fg">{p.title}</p>
                        <p className="mt-0.5 text-sm text-fg-muted">
                          {p.kind === 'QUAL'
                            ? `${p.documents.length} transcript${p.documents.length === 1 ? '' : 's'}`
                            : p.source ? `${p.source.name} · ${p.rows.toLocaleString()} records · ${p.analyses.length} analys${p.analyses.length === 1 ? 'is' : 'es'}` : 'No data yet'}
                          {p.reports.length > 0 && ' · report written'}
                        </p>
                        <p className="mt-0.5 text-xs text-fg-subtle">Kept until {formatDate(p.expiresAt)} unless you work on it again.</p>
                      </Link>
                    </li>
                  ))}
                  {mine.length === 0 && <li className="px-1 text-sm text-fg-subtle">No {k.kind === 'QUAL' ? 'qualitative' : 'quantitative'} analyses yet.</li>}
                </ul>
              )}
            </section>
          )
        })}
      </div>
    </>
  )
}
