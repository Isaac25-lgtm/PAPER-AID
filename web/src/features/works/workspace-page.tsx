import { useCallback, useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/field'
import { Alert, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { walletChanged } from '../../lib/use-wallet'
import type { ReadinessItem } from '../../lib/proposal-types'
import type { Budget, ResultsModel, Work, WorkDocumentView } from '../../lib/work-types'
import { StartProgress, StoppedCard, type Phase } from '../start/progress'
import { ChangeBox, ChecksList, DocFigure, DocTable, ErrorNote, PanelSection, Paper, Para, Versions, WorkspaceHeader, type CheckLine, type WorkspaceStatus } from '../workspace/parts'
import { KIND_LABELS, VARIANT_LABELS } from './shared'
import { LegacyWorkPage } from './work-page'

const START: Record<Work['kind'], string> = { COURSEWORK: '/app/start/coursework', CONCEPT_NOTE: '/app/start/concept-note', FUNDING_PROPOSAL: '/app/start/funding' }

const ESTIMATES: Record<Work['kind'], string> = {
  COURSEWORK: 'This usually takes 8 to 15 minutes.',
  CONCEPT_NOTE: 'This usually takes 10 to 20 minutes.',
  FUNDING_PROPOSAL: 'This usually takes 15 to 30 minutes.',
}

/** A work: while PaperAid works, its progress; when it stopped, why; once written, the workspace.
 *  Works set up before one Start (owner decision 2026-10-01) keep their earlier page until written. */
export function WorkPage() {
  const { workId = '' } = useParams()
  const data = useData()
  const [work, setWork] = useState<Work | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)
  useTitle(work?.plan?.title ?? work?.inputs.title ?? 'Your work')

  const load = useCallback(() => {
    data.works
      .get(workId)
      .then(setWork)
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load this work.'))
  }, [data, workId])
  useEffect(load, [load])
  const onStepDone = useCallback(() => {
    walletChanged()
    window.setTimeout(load, 1200) // the next step (the draft after the plan) is claimed right after
  }, [load])

  if (error && !work)
    return (
      <Alert tone="danger" title="We could not load this work" action={<Button size="sm" variant="secondary" onClick={() => (setError(null), load())}>Try again</Button>}>
        {error}
      </Alert>
    )
  if (work === undefined) return <Skeleton className="h-96 rounded-2xl" />
  if (work === null) return <Alert tone="warning">We couldn't find this work.</Alert>
  // Set up but never started, and no plan yet: it continues on the Start page with its details kept (a
  // tester's coursework refused at Start must not reopen on the earlier plan pages). Older work with a
  // plan keeps its earlier page until written.
  if (!work.auto && !work.documents.length && !work.plan) return <Navigate to={`${START[work.kind]}?work=${work.id}`} replace />
  if (!work.auto && !work.documents.length) return <LegacyWorkPage onWritten={setWork} />

  const retry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      setWork(await data.works.start(work.id))
    } catch (e) {
      setRetryError(e instanceof DataError ? e.message : 'It could not start. Try again.')
    } finally {
      setRetrying(false)
    }
  }

  if (!work.documents.length) {
    if (work.activeJob) {
      const phase: Phase = work.needsRead ? 'read' : work.plan && work.planStatus === 'APPROVED' ? 'write' : 'plan'
      return <StartProgress key={work.activeJob} jobId={work.activeJob} phase={phase} title={`Writing your ${KIND_LABELS[work.kind].toLowerCase()}`} estimate={ESTIMATES[work.kind]} onDone={onStepDone} />
    }
    if (work.autoFailure) return <StoppedCard message={work.autoFailure} onRetry={retry} busy={retrying} error={retryError} />
    return <StartingSoon onCheck={load} />
  }
  return <Workspace work={work} onChange={setWork} onReload={load} />
}

/** The plan has finished and the draft is being claimed: a moment, then the progress screen. */
function StartingSoon({ onCheck }: { onCheck: () => void }) {
  useEffect(() => {
    const timer = window.setInterval(onCheck, 2500)
    return () => window.clearInterval(timer)
  }, [onCheck])
  return <Skeleton className="mx-auto h-72 max-w-2xl rounded-2xl" />
}

/** The figures only the applicant gives that are still missing (the same list the panel asks for). */
function missingFigures(work: Work) {
  const indicators = (work.results?.indicators ?? []).filter((i) => i.target === null || (i.baseline === null && !i.baselinePlan && i.level !== 'output'))
  const lines = (work.budget?.lines ?? []).filter((l) => !l.quantity || !l.unitCost)
  return { indicators, lines, count: indicators.length + lines.length }
}

function statusOf(doc: WorkDocumentView, figures: number): WorkspaceStatus {
  if (doc.exploratory) return { label: 'Exploratory draft', tone: 'warn' }
  const yours = figures || doc.readiness.filter((i) => i.basis === 'AUTHOR' && !['PASS', 'NOT_APPLICABLE'].includes(i.status)).length
  if (doc.status === 'NOT_READY') return yours ? { label: `Needs your input (${yours})`, tone: 'input' } : { label: 'Check before you submit', tone: 'danger' }
  if (doc.status === 'READY_WITH_WARNINGS') return { label: 'Ready with warnings', tone: 'warn' }
  return { label: 'Ready', tone: 'ready' }
}

function lines(items: ReadinessItem[]): CheckLine[] {
  return items
    .filter((i) => i.status !== 'NOT_APPLICABLE' && i.severity !== 'INFO')
    .map((i) => ({ id: i.id, ok: i.status === 'PASS', text: i.question, note: i.status === 'PASS' ? undefined : i.note, action: i.action, yours: i.basis === 'AUTHOR' }))
}

function Workspace({ work, onChange, onReload }: { work: Work; onChange: (w: Work) => void; onReload: () => void }) {
  const data = useData()
  const [doc, setDoc] = useState<WorkDocumentView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const running = Boolean(work.activeJob)

  useEffect(() => {
    if (!running) walletChanged() // what was reserved for the step just finished is settled now
  }, [running])

  useEffect(() => {
    let current = true
    setDoc(null)
    setError(null)
    data.works
      .document(work.id, work.current)
      .then((value) => { if (current) setDoc(value) })
      .catch((e: unknown) => { if (current) setError(e instanceof DataError ? e.message : 'We could not load the document.') })
    return () => { current = false }
  }, [data, work.id, work.current])

  // A change is being applied: check until the new version is saved, then show it.
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(onReload, 4000)
    return () => window.clearInterval(timer)
  }, [running, onReload])

  if (!doc) return error ? <Alert tone="danger">{error}</Alert> : <Skeleton className="h-96 rounded-2xl" />
  const fileName = `${doc.title.slice(0, 70)}.docx`
  const failed = (e: unknown) => setError(e instanceof DataError ? e.message : 'The file could not be prepared.')
  const gaps = doc.readiness.filter((i) => i.basis === 'AUTHOR' && !['PASS', 'NOT_APPLICABLE'].includes(i.status)).length

  const download = async (pdf: boolean) => {
    if (gaps && !window.confirm(`${gaps} place${gaps === 1 ? ' still needs' : 's still need'} your information. They are marked in the document. Download anyway?`)) return
    await (pdf ? data.works.downloadPdf(work.id, fileName.replace(/\.docx$/, '.pdf'), work.current) : data.works.download(work.id, fileName, work.current)).catch(failed)
  }

  const apply = async (text: string, part: string, file: File | null) => {
    setBusy(true)
    setError(null)
    try {
      const sections = part ? [part] : []
      const asked = file ? await data.works.requestChangesWithDocument(work.id, text, sections, file) : await data.works.requestChanges(work.id, text, sections)
      onChange(asked)
      const quoted = await data.works.quoteStep(work.id, 'REVISE', '')
      await data.works.submitStep(work.id, quoted.job.id, quoted.quote.id)
      walletChanged()
      onReload()
      return true
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'Your changes could not start. Try again.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const status = statusOf(doc, missingFigures(work).count)
  const meta = `${KIND_LABELS[work.kind]} · ${VARIANT_LABELS[work.variant]} · ${doc.words.toLocaleString()} words`
  return (
    <>
      <WorkspaceHeader title={doc.title} meta={meta} status={status} onWord={() => download(false)} onPdf={() => download(true)} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="min-w-0">
          <Paper>
            <h1 className="text-center text-xl leading-snug font-semibold">{doc.title}</h1>
            {doc.exploratory && <p className="mt-2 text-center text-sm italic">Exploratory draft: not every eligibility criterion is met.</p>}
            {doc.sections.map((s) => (
              <section key={s.key} className="mt-7">
                <h2 className="text-[17px] font-semibold">{s.heading}</h2>
                {s.paragraphs.map((p, i) => (
                  <Para key={i} text={p} changed={doc.revised.includes(s.key)} />
                ))}
                {s.fieldLimit && <p className="mt-1 text-xs italic">{s.fieldCount} (limit {s.fieldLimit})</p>}
                {s.table && <DocTable caption={s.tableCaption || s.heading} rows={s.table} />}
                {s.figure && <DocFigure figure={s.figure} />}
              </section>
            ))}
            {doc.tables.map((t) => (
              <DocTable key={t.caption} caption={t.caption} rows={t.rows} />
            ))}
            {doc.references.length > 0 && (
              <section className="mt-8">
                <h2 className="text-[17px] font-semibold">References</h2>
                <ul className="mt-2 space-y-1.5">
                  {doc.references.map((r) => (
                    <li key={r} className="pl-8 -indent-8">
                      {r}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {doc.aiNote && <p className="mt-10 border-t border-[#ccc] pt-3 text-sm">{doc.aiNote}</p>}
          </Paper>
        </div>
        <aside className="space-y-4 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
          <ErrorNote text={error} />
          {doc.revised.length > 0 && <p className="rounded-lg bg-brand-50 p-3 text-xs text-brand-900">Highlighted on the page: what changed after your request.</p>}
          {(work.kind === 'FUNDING_PROPOSAL' || work.kind === 'CONCEPT_NOTE') && work.results && (
            <FiguresPanel work={work} onChange={onChange} disabled={running} />
          )}
          <PanelSection title="Ask for changes">
            <ChangeBox parts={doc.sections.map((s) => ({ key: s.key, label: s.heading }))} busy={busy} running={running} onApply={apply} />
          </PanelSection>
          <PanelSection title="What PaperAid checked" defaultOpen={status.tone !== 'ready'}>
            <ChecksList lines={lines(doc.readiness)} />
          </PanelSection>
          {work.documents.length > 1 && (
            <PanelSection title="Versions" defaultOpen={false}>
              <Versions versions={work.documents} current={work.current} onPick={(v) => data.works.setVersion(work.id, v).then(onChange).catch(failed)} />
            </PanelSection>
          )}
        </aside>
      </div>
    </>
  )
}

/** The figures only the applicant can give (owner decision 2026-10-01): entered here, they go into the
 *  logframe, budget and text of the current document as a new version, without AI or a charge. */
function FiguresPanel({ work, onChange, disabled }: { work: Work; onChange: (w: Work) => void; disabled: boolean }) {
  const data = useData()
  const [results, setResults] = useState<ResultsModel>(work.results!)
  const [budget, setBudget] = useState<Budget | null>(work.budget)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => setResults(work.results!), [work.results])
  useEffect(() => setBudget(work.budget), [work.budget])
  const { indicators, lines } = missingFigures(work)
  if (!indicators.length && !lines.length) return null
  const setIndicator = (id: string, patch: Partial<ResultsModel['indicators'][number]>) =>
    setResults((r) => ({ ...r, indicators: r.indicators.map((i) => (i.id === id ? { ...i, ...patch } : i)) }))
  const setLine = (id: string, patch: Partial<Budget['lines'][number]>) => setBudget((b) => (b ? { ...b, lines: b.lines.map((l) => (l.id === id ? { ...l, ...patch } : l)) } : b))
  const num = (v: string) => (v.trim() === '' ? null : Number(v.replace(/,/g, '')))

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      let w = await data.works.saveResults(work.id, results, work.resultsVersion)
      if (budget) w = await data.works.saveBudget(work.id, budget, w.budgetVersion)
      onChange(await data.works.applyFigures(work.id))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'Your figures could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PanelSection title="Needs your input" badge={<span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{indicators.length + lines.length}</span>}>
      <p className="mb-3 text-sm text-fg-muted">Add your figures. They go straight into the logframe, budget and text. PaperAid never invents your figures.</p>
      <div className="space-y-4">
        {indicators.map((ind) => {
          const now = results.indicators.find((i) => i.id === ind.id)!
          return (
            <div key={ind.id}>
              <p className="text-sm font-semibold text-fg">{ind.definition}</p>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                <Input label={`Baseline${ind.unit ? ` (${ind.unit})` : ''}`} inputMode="decimal" value={now.baseline ?? ''} onChange={(e) => setIndicator(ind.id, { baseline: num(e.target.value) })} />
                <Input label={`Target${ind.unit ? ` (${ind.unit})` : ''}`} inputMode="decimal" value={now.target ?? ''} onChange={(e) => setIndicator(ind.id, { target: num(e.target.value) })} />
              </div>
            </div>
          )
        })}
        {budget &&
          lines.map((line) => {
            const now = budget.lines.find((l) => l.id === line.id)!
            return (
              <div key={line.id}>
                <p className="text-sm font-semibold text-fg">{line.description}</p>
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  <Input label={`Quantity${line.unit ? ` (${line.unit})` : ''}`} inputMode="decimal" value={now.quantity || ''} onChange={(e) => setLine(line.id, { quantity: num(e.target.value) ?? 0 })} />
                  <Input label={`Unit cost (${budget.currency})`} inputMode="decimal" value={now.unitCost || ''} onChange={(e) => setLine(line.id, { unitCost: num(e.target.value) ?? 0 })} />
                </div>
              </div>
            )
          })}
      </div>
      <ErrorNote text={error} />
      <Button className="mt-4 w-full" loading={busy} disabled={disabled} onClick={save}>
        Save figures
      </Button>
    </PanelSection>
  )
}
