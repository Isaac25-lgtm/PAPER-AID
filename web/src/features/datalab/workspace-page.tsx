import { clsx } from 'clsx'
import { CheckCircle2, ChevronDown, Download, FileSpreadsheet, Loader2, RotateCcw, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Checkbox, Select, TextArea } from '../../components/ui/field'
import { Alert, Badge, Card, Skeleton } from '../../components/ui/primitives'
import type { AnalysisKind, AnalysisResult, AnalysisSpec, DataOp, DataPreview, DataProject, DataVariable, ReportDocument, UploadChoice, VariableKind } from '../../lib/datalab-types'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { AnalysisForm } from './analysis-form'
import { QualWorkspace } from './qual-workspace'
import { UploadCard } from './upload'
import { Confirm, FLAG_LABEL, KIND_LABEL, KINDS_FOR, ReportView, ResultCard, title as varTitle } from './parts'

const OP_LABEL: Record<DataOp['kind'], string> = {
  LOAD: 'Reading your data…',
  SHEET: 'Reading the sheet…',
  DECIDE: 'Applying the change…',
  UNDO: 'Undoing the change…',
  ANALYSE: 'Running the analysis…',
  CLEANED: 'Preparing your cleaned data…',
}

const working = (p: DataProject | null) => Boolean(p?.op && (p.op.status === 'QUEUED' || p.op.status === 'RUNNING'))

const scrollTo = (id: string) => window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)

/** One part of the page, numbered, that can be folded away once done. */
function Section({ id, n, title, note, open: initiallyOpen = true, children }: { id: string; n: number; title: string; note?: ReactNode; open?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(initiallyOpen)
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20 space-y-4">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-3 border-b border-line pb-2 text-left">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-700 text-sm font-semibold text-white">{n}</span>
        <h2 id={`${id}-title`} className="flex-1 text-lg font-semibold text-fg">{title}</h2>
        {note}
        <ChevronDown className={clsx('size-5 text-fg-subtle transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && children}
    </section>
  )
}

/** A Data Lab project on one page: the data, the checks PaperAid needs confirmed, the analyses and maps, the report. */
export function DataLabWorkspace() {
  const { projectId = '' } = useParams()
  const data = useData()
  const navigate = useNavigate()
  const [project, setProject] = useState<DataProject | null>(null)
  const [missing, setMissing] = useState(false)
  const [params] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const following = useRef(false)
  const busy = acting || working(project)
  useTitle(project?.title ?? 'Data Lab')

  const load = useCallback(async () => {
    const p = await data.datalab.get(projectId)
    if (!p) setMissing(true)
    else setProject(p)
    return p
  }, [data, projectId])

  useEffect(() => {
    load().catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load this project.'))
  }, [load])

  // While the report is being written, look again every few seconds.
  useEffect(() => {
    if (!project?.activeJob) return
    const timer = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(timer)
  }, [project?.activeJob, load])

  /** Data work runs on PaperAid's servers: look again until it has finished, then show its outcome. */
  const follow = useCallback(
    async (start: DataProject): Promise<DataProject> => {
      const watched = working(start)
      let current = start
      setProject(current)
      following.current = true
      try {
        while (working(current)) {
          await new Promise((resolve) => window.setTimeout(resolve, 700))
          const next = await data.datalab.get(current.id)
          if (!next) {
            setMissing(true)
            return current
          }
          current = next
          setProject(current)
        }
      } finally {
        following.current = false
      }
      if (watched && current.op?.status === 'FAILED') setError(current.op.error || 'That did not work. Try again.')
      return current
    },
    [data],
  )

  // Work started before the page opened (or in another tab): follow it too.
  useEffect(() => {
    if (project && working(project) && !following.current) void follow(project)
  }, [project, follow])

  const act = async (fn: () => Promise<DataProject | void>): Promise<DataProject | undefined> => {
    setActing(true)
    setError(null)
    try {
      const next = await fn()
      return next ? await follow(next) : undefined
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
      return undefined
    } finally {
      setActing(false)
    }
  }

  const cleaned = async () => {
    const ready = project?.cleanedReady ? project : await act(() => data.datalab.makeCleaned(projectId))
    if (ready?.cleanedReady) await act(() => data.datalab.downloadCleaned(projectId, `${ready.title} - cleaned data`))
  }

  if (missing) return <Alert tone="warning">This project no longer exists. <Link to="/app/datalab" className="font-semibold underline">Back to Data Lab</Link></Alert>
  if (!project) return error ? <Alert tone="danger">{error}</Alert> : <Skeleton className="h-96 rounded-2xl" />
  if (project.kind === 'QUAL') return <QualWorkspace initial={project} />
  const checks = project.pending.length + (project.survey === 'ASK' ? project.surveyColumns.length : 0)

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold tracking-wide text-brand-700 uppercase">
            {project.proposalId ? <Link to={`/app/projects/${project.proposalId}`} className="hover:underline">Research proposal · Chapter Four</Link> : 'Data Lab'}
          </p>
          <h1 className="text-2xl font-bold text-fg">{project.title}</h1>
          {project.source && (
            <p className="text-sm text-fg-muted">
              {project.source.name}
              {project.source.sheet && ` · sheet "${project.source.sheet}"`} · {project.rows.toLocaleString()} records · {project.columns} variables · version {project.version}
            </p>
          )}
        </div>
        {project.source && (
          <>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => act(() => data.datalab.downloadWorkbook(project.id, `${project.title}.xlsx`))}
              title="Your results with their tables and charts, safe to share: no individual records">
              <FileSpreadsheet className="size-4" aria-hidden /> Report workbook
            </Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => void cleaned()}
              title="Your cleaned records, for your own use: columns that may identify people stay out unless you included them">
              <Download className="size-4" aria-hidden /> Cleaned data
            </Button>
          </>
        )}
        <Button variant="ghost" size="sm" disabled={busy || Boolean(project.activeJob)}
          onClick={() => {
            if (window.confirm('Delete this project, its data, analyses and reports?')) void act(async () => { await data.datalab.remove(project.id); navigate('/app/datalab') })
          }}>
          Delete
        </Button>
      </header>

      {working(project) && project.op && (
        <Card className="flex items-center gap-3 p-4" role="status">
          <Loader2 className="size-5 animate-spin text-brand-700" aria-hidden />
          <p className="text-sm font-medium text-fg">{OP_LABEL[project.op.kind]}</p>
        </Card>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      <Section id="data" n={1} title="Your data" open={!project.source}
        note={project.source ? <span className="text-xs text-fg-muted">{project.columns} variables</span> : undefined}>
        <DataStep project={project} busy={busy} act={act} onLoaded={(p) => scrollTo(p.pending.length || p.survey === 'ASK' ? 'checks' : 'analyses')} />
      </Section>
      {project.source && (
        <>
          <Section id="checks" n={2} title="Checks" open={checks > 0}
            note={checks > 0 ? <span className="rounded-full bg-amber-100 px-2 text-xs text-amber-900">{checks} to confirm</span> : <span className="text-xs text-fg-muted">Done</span>}>
            <CheckStep project={project} busy={busy} act={act} onDone={() => scrollTo('analyses')} />
          </Section>
          <Section id="analyses" n={3} title="Analyses and maps"
            note={project.analyses.length > 0 ? <span className="text-xs text-fg-muted">{project.analyses.length} run</span> : undefined}>
            <AnalyseStep project={project} busy={busy} act={act} goReport={() => scrollTo('report')} startWith={params.get('map') ? 'MAP' : null} />
          </Section>
          <Section id="report" n={4} title={project.proposalId ? 'Chapter Four' : 'Report'}>
            <ReportStep project={project} busy={busy} act={act} reload={load} />
          </Section>
        </>
      )}
    </div>
  )
}

type Act = (fn: () => Promise<DataProject | void>) => Promise<DataProject | undefined>

function DataStep({ project, busy, act, onLoaded }: { project: DataProject; busy: boolean; act: Act; onLoaded: (p: DataProject) => void }) {
  const data = useData()
  const [preview, setPreview] = useState<DataPreview | null>(null)
  const [replacing, setReplacing] = useState(false)
  const upload = async (file: File, choice: UploadChoice) => {
    const done = await act(() => data.datalab.upload(project.id, file, choice))
    if (done?.op?.status === 'DONE') {
      setReplacing(false)
      onLoaded(done)
    }
  }
  if (!project.source || replacing)
    return (
      <div className="space-y-3">
        <UploadCard retentionDays={data.config.retentionDays} busy={busy} onUpload={(f, c) => void upload(f, c)} compact={replacing}
          onCancel={replacing ? () => setReplacing(false) : undefined} />
        {replacing && <p className="text-sm text-fg-muted">A new file starts the data again: analyses on the current data are removed; reports already written are kept.</p>}
        <p className="text-sm text-fg-muted">PaperAid reads values only: formulas are never run. Columns that may identify people or places are left out of the analysis unless you include them.</p>
      </div>
    )
  return (
    <div className="space-y-5">
      {project.released.length > 0 && (
        <Alert tone="info">
          You included {project.released.map((r) => `"${r.name}"`).join(', ')}, which may identify people or places. The report's methods say so, and the cleaned data
          includes {project.released.length === 1 ? 'it' : 'them'}.
        </Alert>
      )}
      {project.source.sheets.length > 1 && (
        <Card className="flex flex-wrap items-end gap-3 p-4">
          <Select label="Sheet analysed" value={project.source.sheet ?? ''} disabled={busy}
            onChange={(e) => {
              const name = e.target.value
              if (window.confirm('Analyse another sheet? This starts the data again: analyses on this sheet are removed.')) void act(() => data.datalab.chooseSheet(project.id, name))
            }}>
            {project.source.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Card>
      )}
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[46rem] text-sm">
          <thead>
            <tr className="border-b border-line bg-surface-subtle text-left text-fg-muted">
              <th className="px-3 py-2 font-medium">Variable</th>
              <th className="px-3 py-2 font-medium">Label</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Values</th>
              <th className="px-3 py-2 font-medium">Missing</th>
              <th className="px-3 py-2 font-medium">Included</th>
            </tr>
          </thead>
          <tbody>
            {project.variables.map((v) => <VariableRow key={v.name} project={project} variable={v} busy={busy} act={act} />)}
          </tbody>
        </table>
      </Card>
      {project.source.removed.length > 0 && (
        <p className="text-sm text-fg-muted">Removed on your device before upload: {project.source.removed.join(', ')}.</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy} onClick={() => act(async () => setPreview(await data.datalab.preview(project.id)))}>See the data</Button>
        <Button variant="secondary" disabled={busy} onClick={() => setReplacing(true)}>Upload a different file</Button>
      </div>
      {preview && (
        <Card className="overflow-x-auto p-0">
          <p className="px-4 pt-3 text-xs text-fg-muted">The first {preview.rows.length} of {preview.total.toLocaleString()} records. Columns left out are shown as •••.</p>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="bg-surface-subtle">{preview.columns.map((c) => <th key={c} className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{c}</th>)}</tr></thead>
            <tbody>{preview.rows.map((row, i) => <tr key={i} className="border-t border-line">{row.map((cell, j) => <td key={j} className="px-2 py-1 whitespace-nowrap">{cell}</td>)}</tr>)}</tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function VariableRow({ project, variable: v, busy, act }: { project: DataProject; variable: DataVariable; busy: boolean; act: Act }) {
  const data = useData()
  const [label, setLabel] = useState(v.label)
  const total = v.valid + v.missing
  const values = v.stored === 'number' && v.summary.mean !== undefined
    ? `mean ${v.summary.mean.toFixed(2)}, ${v.summary.min} to ${v.summary.max}`
    : v.levels.slice(0, 3).map((l) => `${l.value} (${l.count})`).join(', ') + (v.levels.length > 3 ? ', …' : '')
  return (
    <tr className="border-b border-line align-top last:border-0">
      <td className="px-3 py-2">
        <p className="font-medium text-fg">{v.name}</p>
        <div className="mt-1 flex flex-wrap gap-1">{v.flags.map((f) => <Badge key={f} tone={f === 'PERSONAL' || f === 'SURVEY_DESIGN' ? 'warning' : 'neutral'}>{FLAG_LABEL[f]}</Badge>)}</div>
      </td>
      <td className="px-3 py-2">
        <input aria-label={`Label for ${v.name}`} className="w-40 rounded-md border border-line px-2 py-1 text-sm" value={label} maxLength={120} disabled={busy}
          onChange={(e) => setLabel(e.target.value)} onBlur={() => { if (label !== v.label) void act(() => data.datalab.editVariable(project.id, v.name, { label })) }} />
      </td>
      <td className="px-3 py-2">
        <select aria-label={`Type of ${v.name}`} className="rounded-md border border-line px-2 py-1 text-sm" value={v.kind} disabled={busy}
          onChange={(e) => act(() => data.datalab.editVariable(project.id, v.name, { kind: e.target.value as VariableKind }))}>
          {KINDS_FOR[v.stored].filter((k) => k !== 'BINARY' || v.distinct === 2).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
      </td>
      <td className="max-w-56 px-3 py-2 text-fg-muted">{values}</td>
      <td className="px-3 py-2 tabular-nums text-fg-muted">{v.missing ? `${v.missing.toLocaleString()} (${((100 * v.missing) / total).toFixed(1)}%)` : 'None'}</td>
      <td className="px-3 py-2">
        <input type="checkbox" aria-label={`Include ${v.name} in analysis`} className="size-4 accent-brand-700" checked={!v.excluded} disabled={busy}
          onChange={(e) => {
            const include = e.target.checked
            const sensitive = v.flags.includes('PERSONAL') || v.flags.includes('LOCATION')
            if (include && sensitive && !window.confirm(`"${v.name}" may identify people or places. Include it anyway? Your choice is recorded and named in the report's methods.`)) return
            void act(() => data.datalab.editVariable(project.id, v.name, { excluded: !include }))
          }} />
      </td>
    </tr>
  )
}

function CheckStep({ project, busy, act, onDone }: { project: DataProject; busy: boolean; act: Act; onDone: () => void }) {
  const data = useData()
  const asked = project.variables.filter((v) => project.surveyColumns.includes(v.name))
  const next = project.pending[0]
  const undoable = project.applied.some((s) => !s.automatic && s.version === project.version)
  return (
    <div className="space-y-5">
      {asked.map((v) => (
        <div key={v.name} className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-5">
          <p className="text-base font-medium text-fg">What is "{varTitle(v)}"?</p>
          <p className="text-sm text-fg-muted">Its name suggests it may describe how a survey's sample was drawn (a weight, a cluster or a stratum). Results that ignore a survey's design can be misleading.</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={busy} onClick={() => act(() => data.datalab.editVariable(project.id, v.name, { survey: 'DESIGN' }))}>It's a survey weight, cluster or stratum</Button>
            <Button variant="secondary" disabled={busy} onClick={() => act(() => data.datalab.editVariable(project.id, v.name, { survey: 'NOT_DESIGN' }))}>It's something else</Button>
          </div>
        </div>
      ))}
      {project.survey === 'DESIGN' && (
        <Alert tone="warning">This dataset comes from a survey with a sampling design. PaperAid can't yet analyse such data correctly, so it won't run analyses that would ignore the design. You can still review the data and its quality.</Alert>
      )}
      {next ? (
        <Confirm question={next.question} busy={busy} more={project.pending.length - 1}
          onYes={() => act(() => data.datalab.decide(project.id, next.id, true))} onNo={() => act(() => data.datalab.decide(project.id, next.id, false))} />
      ) : (
        project.survey !== 'ASK' && (
          <Alert tone="success" title="Nothing else needs your confirmation">
            <span className="block">The data is ready to analyse. </span>
            <Button className="mt-2" size="sm" onClick={onDone}>Choose an analysis</Button>
          </Alert>
        )
      )}
      {project.applied.length > 0 && (
        <Card className="space-y-2 p-5">
          <div className="flex items-center gap-2">
            <h2 className="flex-1 text-base font-semibold">Changes made</h2>
            {undoable && <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(() => data.datalab.undo(project.id))}><RotateCcw className="size-4" aria-hidden /> Undo the last change</Button>}
          </div>
          <ul className="space-y-1.5">
            {project.applied.map((s) => (
              <li key={s.id} className="flex gap-2 text-sm text-fg">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
                <span>{s.description} <span className="text-fg-subtle">({s.automatic ? 'automatic' : 'you confirmed'}{s.version ? `, version ${s.version}` : ''})</span></span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-fg-subtle">Your original file is never changed: each change makes a new version.</p>
        </Card>
      )}
    </div>
  )
}

const QUESTIONS: { kind: AnalysisKind; title: string; body: string }[] = [
  { kind: 'DESCRIBE', title: 'Describe one variable', body: 'Counts and percentages, or the average and spread.' },
  { kind: 'COMPARE_TWO', title: 'Compare two groups', body: 'Does a number differ between two groups?' },
  { kind: 'CROSSTAB', title: 'Are two categories related?', body: 'For example, does the answer differ by district?' },
  { kind: 'CORRELATE', title: 'Do two numbers go together?', body: 'Do higher values of one go with higher (or lower) values of the other?' },
  { kind: 'MAP', title: 'Map of Uganda', body: 'By district, subcounty, sub-region or region: counts, averages, totals or rates.' },
]

function AnalyseStep({ project, busy, act, goReport, startWith }: { project: DataProject; busy: boolean; act: Act; goReport: () => void; startWith: AnalysisKind | null }) {
  const data = useData()
  const [kind, setKind] = useState<AnalysisKind | null>(startWith)
  const [results, setResults] = useState<Record<string, AnalysisResult>>({})
  const [error, setError] = useState<string | null>(null)
  const usable = project.variables.filter((v) => !v.excluded)
  const numbers = usable.filter((v) => v.kind === 'NUMERIC')
  const categories = usable.filter((v) => v.kind === 'CATEGORICAL' || v.kind === 'BINARY')

  useEffect(() => {
    const wanted = project.analyses.filter((a) => !results[a.id])
    if (!wanted.length) return
    Promise.all(wanted.map((a) => data.datalab.analysis(project.id, a.id)))
      .then((list) => setResults((r) => ({ ...r, ...Object.fromEntries(list.map((x) => [x.id, x])) })))
      .catch(() => setError('Some results could not be loaded. Reload the page.'))
  }, [data, project.id, project.analyses]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (spec: AnalysisSpec) => {
    setError(null)
    const done = await act(() => data.datalab.analyse(project.id, spec))
    if (done?.op?.kind === 'ANALYSE' && done.op.status === 'DONE' && done.op.result) {
      const id = done.op.result
      try {
        const result = await data.datalab.analysis(project.id, id)
        setResults((r) => ({ ...r, [id]: result }))
        setKind(null)
      } catch {
        setError('The result could not be loaded. Reload the page.')
      }
    }
  }

  const blocked = project.survey !== 'NONE'
  return (
    <div className="space-y-5">
      {blocked && <Alert tone="warning">{project.survey === 'ASK' ? 'First answer the question about the survey design (step 2).' : 'This dataset has a survey design PaperAid can’t analyse correctly yet.'}</Alert>}
      {!blocked && (
        <Card className="space-y-4 p-5 sm:p-6">
          <h2 className="text-lg font-semibold">What do you want to know?</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {QUESTIONS.map((q) => (
              <button key={q.kind} onClick={() => setKind(q.kind)} aria-pressed={kind === q.kind}
                className={clsx('rounded-xl border p-4 text-left transition', kind === q.kind ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600' : 'border-line hover:border-brand-300')}>
                <p className="font-semibold text-fg">{q.title}</p>
                <p className="mt-0.5 text-sm text-fg-muted">{q.body}</p>
              </button>
            ))}
          </div>
          {kind && <AnalysisForm kind={kind} numbers={numbers} categories={categories} usable={usable} busy={busy} onRun={run} objectives={project.objectives} />}
          {error && <Alert tone="danger">{error}</Alert>}
        </Card>
      )}
      {project.analyses.length > 0 && (
        <div className="flex items-center gap-3">
          <h2 className="flex-1 text-lg font-semibold">Your results</h2>
          <Button size="sm" onClick={goReport}><Sparkles className="size-4" aria-hidden /> Write the report</Button>
        </div>
      )}
      {project.analyses.map((a) =>
        results[a.id] ? (
          <ResultCard key={a.id} projectId={project.id} result={results[a.id]} stale={a.stale}
            onRemove={() => void act(() => data.datalab.removeAnalysis(project.id, a.id))}
            onUseMatches={results[a.id].spec.kind === 'MAP' ? () => run({ ...results[a.id].spec, aliases: { ...(results[a.id].spec.aliases ?? {}), ...results[a.id].matches } }) : undefined} />
        ) : (
          <Skeleton key={a.id} className="h-40 rounded-2xl" />
        ),
      )}
    </div>
  )
}

function ReportStep({ project, busy, act, reload }: { project: DataProject; busy: boolean; act: Act; reload: () => Promise<DataProject | null> }) {
  const data = useData()
  const current = project.analyses.filter((a) => !a.stale && a.status !== 'NOT_ESTIMABLE')
  const outOfDate = project.analyses.filter((a) => a.stale).length
  const [chosen, setChosen] = useState<string[]>(current.map((a) => a.id))
  // On one page the report form is open while analyses are run: each new one starts ticked.
  const seen = useRef(new Set(current.map((a) => a.id)))
  const fresh = current.filter((a) => !seen.current.has(a.id)).map((a) => a.id)
  useEffect(() => {
    if (!fresh.length) return
    fresh.forEach((id) => seen.current.add(id))
    setChosen((c) => [...c, ...fresh])
  }, [fresh.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  const [noAnalysisOk, setNoAnalysisOk] = useState(false)
  const covered = new Set(current.filter((a) => chosen.includes(a.id) && a.objective !== null).map((a) => a.objective))
  const uncovered = project.proposalId ? project.objectives.map((_, i) => i + 1).filter((k) => !covered.has(k)) : []
  const [purpose, setPurpose] = useState(project.purpose)
  const [report, setReport] = useState<ReportDocument | null>(null)
  const name = project.title || 'Analysis report'

  useEffect(() => {
    if (!project.reports.length) return
    data.datalab.report(project.id).then(setReport).catch(() => setReport(null))
  }, [data, project.id, project.reportCurrent, project.reports.length])

  const start = () =>
    act(async () => {
      if (purpose !== project.purpose) await data.datalab.update(project.id, { purpose })
      await data.datalab.startReport(project.id, chosen, noAnalysisOk ? uncovered : [])
      await reload()
    })

  return (
    <div className="space-y-5">
      {project.activeJob ? (
        <Card className="flex items-center gap-3 p-5" role="status">
          <Loader2 className="size-5 animate-spin text-brand-700" aria-hidden />
          <p className="text-sm font-medium text-fg">Writing your {project.proposalId ? 'Chapter Four' : 'analysis report'}… this usually takes a few minutes. It opens here when it is ready.</p>
        </Card>
      ) : (
        <Card className="space-y-4 p-5 sm:p-6">
          <h2 className="text-lg font-semibold">{project.proposalId ? (project.reports.length ? 'Write Chapter Four again' : 'Write Chapter Four') : project.reports.length ? 'Write the report again' : 'Write your analysis report'}</h2>
          {!project.reportPriced && <Alert tone="info">The analysis report isn't available yet. Your analyses and the Excel workbook are.</Alert>}
          {project.reportFailure && <Alert tone="warning">{project.reportFailure}</Alert>}
          {outOfDate > 0 && (
            <p className="text-sm text-fg-muted">
              {outOfDate === 1 ? '1 result is' : `${outOfDate} results are`} out of date (the data or a setting changed after {outOfDate === 1 ? 'it' : 'they'} ran) and
              can't go in the report. Run {outOfDate === 1 ? 'it' : 'them'} again in step 3.
            </p>
          )}
          {current.length === 0 ? (
            <p className="text-sm text-fg-muted">Run at least one analysis on the current data first.</p>
          ) : (
            <>
              {!project.proposalId && (
                <TextArea label="What do you want to find out?" rows={2} maxLength={1500} value={purpose} onChange={(e) => setPurpose(e.target.value)}
                  hint="The report's summary starts from your question." />
              )}
              {project.proposalId && current.some((a) => a.objective === null) && (
                <p className="text-sm text-fg-muted">Analyses not tied to an objective appear under "Other results".</p>
              )}
              <fieldset className="space-y-1.5">
                <legend className="mb-1 text-sm font-medium text-fg">Analyses in the {project.proposalId ? 'chapter' : 'report'}</legend>
                {current.map((a) => (
                  <div key={a.id} className="flex flex-wrap items-center gap-2">
                    <Checkbox className="min-w-0 flex-1" label={a.title} checked={chosen.includes(a.id)}
                      onChange={(e) => setChosen(e.target.checked ? [...chosen, a.id] : chosen.filter((x) => x !== a.id))} />
                    {project.proposalId && (
                      <select aria-label={`Objective answered by ${a.title}`} className="max-w-full rounded-md border border-line px-2 py-1 text-xs" value={a.objective ?? ''}
                        disabled={busy} onChange={(e) => void act(() => data.datalab.setObjective(project.id, a.id, e.target.value ? Number(e.target.value) : null))}>
                        <option value="">Other results</option>
                        {project.objectives.map((o, i) => <option key={o} value={String(i + 1)}>{`Objective ${i + 1}`}</option>)}
                      </select>
                    )}
                  </div>
                ))}
              </fieldset>
              {uncovered.length > 0 && (
                <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                  <p className="text-sm text-fg">
                    No analysis answers {uncovered.length === 1 ? 'objective' : 'objectives'} {uncovered.join(', ')}. Run one in step 3, or let Chapter Four say so.
                  </p>
                  <Checkbox label={`Write Chapter Four saying that no analysis was reported for ${uncovered.length === 1 ? 'this objective' : 'these objectives'}`}
                    checked={noAnalysisOk} onChange={(e) => setNoAnalysisOk(e.target.checked)} />
                </div>
              )}
              <Button loading={busy} disabled={!project.reportPriced || chosen.length === 0 || (uncovered.length > 0 && !noAnalysisOk)} onClick={start}>
                <Sparkles className="size-4" aria-hidden /> {project.proposalId ? 'Write Chapter Four' : 'Write my analysis report'}
              </Button>
              <p className="text-xs text-fg-subtle">Every number in the report is calculated by PaperAid's code from your data; the text explains them.</p>
            </>
          )}
        </Card>
      )}
      {report && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => act(() => data.datalab.downloadReport(project.id, `${name}.docx`))}><Download className="size-4" aria-hidden /> Download Word</Button>
            <Button variant="secondary" disabled={busy} onClick={() => act(() => data.datalab.downloadReportPdf(project.id, `${name}.pdf`))}><Download className="size-4" aria-hidden /> PDF</Button>
            <Button variant="secondary" disabled={busy} onClick={() => act(() => data.datalab.downloadWorkbook(project.id, `${name}.xlsx`))}><FileSpreadsheet className="size-4" aria-hidden /> Report workbook</Button>
          </div>
          <ReportView projectId={project.id} report={report} />
        </>
      )}
    </div>
  )
}
