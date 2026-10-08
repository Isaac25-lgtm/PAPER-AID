import { clsx } from 'clsx'
import { ChartColumn, Check, Wrench } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/field'
import { Alert, Card, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { ChapterView, Project, ReadinessItem } from '../../lib/proposal-types'
import { useTitle } from '../../lib/use-title'
import { usePageRecord } from '../../lib/use-page-record'
import { walletChanged } from '../../lib/use-wallet'
import { StartProgress, StoppedCard } from '../start/progress'
import { ChangeBox, ChecksList, DocTable, ErrorNote, PanelSection, Paper, Para, Versions, WorkspaceHeader, type CheckLine, type WorkspaceStatus } from '../workspace/parts'
import { ProjectPage as LegacyProjectPage } from './project-page'

const CONCEPT = 4
type Num = 1 | 2 | 3 | 4
const NAMES: Record<number, string> = { 1: 'Chapter One', 2: 'Chapter Two', 3: 'Chapter Three', 4: 'Concept paper' }

/** A research proposal (owner decision 2026-10-01): while PaperAid works, its progress; when it
 *  stopped, why; once a chapter is written, the workspace with one tab per chapter. Proposals set up
 *  before one Start keep their earlier page, and its full tools stay one click away ("More tools"). */
export function ProjectPage() {
  const { projectId = '' } = useParams()
  return <SelectedProjectPage key={projectId} projectId={projectId} />
}

function SelectedProjectPage({ projectId }: { projectId: string }) {
  const [params] = useSearchParams()
  const data = useData()
  const read = useCallback(() => data.projects.get(projectId), [data, projectId])
  const { record: project, error, load, change: setProject } = usePageRecord(projectId, read, 'We could not load this proposal.')
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)
  useTitle(project?.plan?.title ?? project?.inputs.topic ?? 'Research proposal')

  const onStepDone = useCallback(() => {
    walletChanged()
    window.setTimeout(load, 1200) // Chapter One is claimed right after the plan
  }, [load])

  if (params.get('tools')) return <LegacyProjectPage />
  if (error && !project)
    return (
      <Alert tone="danger" title="We could not load this proposal" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>
        {error}
      </Alert>
    )
  if (project === undefined) return <Skeleton className="h-96 rounded-2xl" />
  if (project === null) return <Alert tone="warning">This proposal no longer exists.</Alert>
  const first = project.goal === 'CONCEPT' ? CONCEPT : 1
  const written = project.chapters.filter((c) => c.current).map((c) => c.number)
  if (!project.auto && !written.length) return <LegacyProjectPage />

  const sampling = project.autoFailure.startsWith('PaperAid needs one answer') // the standard sample-size settings, not yet confirmed
  const retry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      setProject(await data.projects.start(project.id, sampling))
    } catch (e) {
      setRetryError(e instanceof DataError ? e.message : 'It could not start. Try again.')
    } finally {
      setRetrying(false)
    }
  }

  if (!written.includes(first)) {
    if (project.activeJob)
      return (
        <StartProgress key={project.activeJob} jobId={project.activeJob} phase={project.planStatus === 'APPROVED' ? 'write' : 'plan'}
          title={first === CONCEPT ? 'Writing your concept paper' : 'Writing Chapter One'} estimate="This usually takes 10 to 20 minutes." onDone={onStepDone} />
      )
    if (project.autoFailure)
      return sampling ? (
        <StoppedCard title="We need one answer to continue" retryLabel="Use the standard settings and continue"
          message={`${project.autoFailure} The standard settings are 95% confidence, a 5% margin of error and a 50% expected proportion; the chapter says they were assumed.`}
          onRetry={retry} busy={retrying} error={retryError} />
      ) : (
        <StoppedCard message={project.autoFailure} onRetry={retry} busy={retrying} error={retryError} />
      )
    return <Waiting onCheck={load} />
  }
  return <Workspace project={project} onChange={setProject} onReload={load} />
}

/** The complete proposal: what it still needs, each with its action here (Codex audit 2026-10-01: the
 *  download must not be promised while the server would refuse it). */
/** Chapter Four (owner decision 2026-10-03): once the data is collected, it is analysed by objective in Data Lab. */
function ChapterFourCard({ projectId }: { projectId: string }) {
  const data = useData()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <Card className="space-y-2 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-fg"><ChartColumn className="size-4 text-brand-700" aria-hidden /> Chapter Four: your results</p>
      <p className="text-sm text-fg-muted">When your data is collected, upload it. PaperAid analyses it by your objectives and writes Chapter Four, every number calculated by code.</p>
      <Button variant="secondary" className="w-full" loading={busy}
        onClick={async () => {
          setBusy(true)
          setError(null)
          try {
            navigate(`/app/datalab/${(await data.datalab.forProposal(projectId)).id}`)
          } catch (e) {
            setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
            setBusy(false)
          }
        }}>
        Analyse my data
      </Button>
      <ErrorNote text={error} />
    </Card>
  )
}

function FinishCard({ project, onChange, onDownload }: { project: Project; onChange: (p: Project) => void; onDownload: () => void }) {
  const data = useData()
  const [supervisor, setSupervisor] = useState(project.titlePage.supervisor)
  const [date, setDate] = useState(project.titlePage.submissionDate)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const needsPage = project.blockers.some((b) => /title page/.test(b))
  const others = project.blockers.filter((b) => !/title page/.test(b))
  const saveDetails = async () => {
    setBusy(true)
    setError(null)
    try {
      onChange(await data.projects.updateDetails(project.id, project.inputs, { ...project.titlePage, supervisor, submissionDate: date }, project.citation))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'These details could not be saved.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="p-5">
      <p className="text-base font-semibold">{project.blockers.length ? 'Before your complete proposal' : 'Your proposal is complete'}</p>
      {project.blockers.length === 0 ? (
        <>
          <p className="mt-1 text-sm text-fg-muted">Download all three chapters with the title page, contents and references.</p>
          <Button className="mt-3 w-full" onClick={onDownload}>
            Download complete proposal
          </Button>
        </>
      ) : (
        <div className="mt-2 space-y-3">
          {others.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-sm text-fg-muted">
              {others.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
          {needsPage && (
            <div className="space-y-2">
              <p className="text-sm text-fg-muted">Your title page needs:</p>
              <Input label="Supervisor" required maxLength={160} value={supervisor} onChange={(e) => setSupervisor(e.target.value)} />
              <Input label="Submission date" required maxLength={40} value={date} placeholder="e.g. October 2026" onChange={(e) => setDate(e.target.value)} />
              <Button size="sm" variant="secondary" loading={busy} disabled={!supervisor.trim() || !date.trim()} onClick={saveDetails}>
                Save title page
              </Button>
            </div>
          )}
          <ErrorNote text={error} />
          <p className="text-xs text-fg-subtle">Until then, Download Word above gives the draft with everything written so far.</p>
        </div>
      )}
    </Card>
  )
}

function Waiting({ onCheck }: { onCheck: () => void }) {
  useEffect(() => {
    const timer = window.setInterval(onCheck, 2500)
    return () => window.clearInterval(timer)
  }, [onCheck])
  return <Skeleton className="mx-auto h-72 max-w-2xl rounded-2xl" />
}

function lines(items: ReadinessItem[]): CheckLine[] {
  return items.filter((i) => i.status !== 'NOT_APPLICABLE').map((i) => ({ id: i.id, ok: i.status === 'PASS', text: i.question, note: i.status === 'PASS' ? undefined : i.note, action: i.action, yours: i.basis === 'AUTHOR' }))
}

function Workspace({ project, onChange, onReload }: { project: Project; onChange: (p: Project) => void; onReload: () => void }) {
  const data = useData()
  const concept = project.goal === 'CONCEPT'
  const tabs: Num[] = concept ? [CONCEPT] : [1, 2, 3]
  const written = new Set(project.chapters.filter((c) => c.current).map((c) => c.number))
  const [shown, setShown] = useState<Num>(() => (concept ? CONCEPT : [...tabs].reverse().find((n) => written.has(n)) ?? 1))
  const [chapter, setChapter] = useState<ChapterView | null>(null)
  const [figure, setFigure] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const state = project.chapters.find((c) => c.number === shown)
  const running = Boolean(project.activeJob)

  useEffect(() => {
    let current = true
    setChapter(null)
    setError(null)
    if (!state?.current) return () => { current = false }
    data.projects
      .chapter(project.id, shown, state.current)
      .then((value) => { if (current) setChapter(value) })
      .catch((e: unknown) => { if (current) setError(e instanceof DataError ? e.message : 'We could not load this chapter.') })
    return () => { current = false }
  }, [data, project.id, shown, state?.current])

  useEffect(() => {
    if (!project.framework) {
      setFigure(null)
      return
    }
    let current = true
    let url: string | null = null
    data.projects
      .framework(project.id)
      .then((blob) => {
        url = URL.createObjectURL(blob)
        if (current) setFigure(url)
        else URL.revokeObjectURL(url)
      })
      .catch(() => { if (current) setFigure(null) })
    return () => {
      current = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [data, project.id, project.framework, project.planVersion])

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(onReload, 4000)
    return () => window.clearInterval(timer)
  }, [running, onReload])

  const stem = (project.plan?.title ?? project.inputs.topic).slice(0, 80)
  const failed = (e: unknown) => setError(e instanceof DataError ? e.message : 'The file could not be prepared.')
  const word = async () => {
    await (concept ? data.projects.downloadConcept(project.id, `${stem} – concept paper.docx`) : data.projects.download(project.id, false, `${stem}.docx`)).catch(failed)
  }
  const pdf = async () => {
    await data.projects.downloadPdf(project.id, false, `${stem}.pdf`).catch(failed)
  }

  const apply = async (text: string, part: string, file: File | null) => {
    setBusy(true)
    setError(null)
    try {
      const before = new Set(project.feedback.map((c) => c.id))
      const sections = part ? [part] : []
      const updated = file ? await data.projects.requestChangesWithDocument(project.id, shown, text, sections, file) : await data.projects.requestChanges(project.id, shown, text, sections)
      onChange(updated)
      const mine = updated.feedback.find((c) => c.by === 'STUDENT' && !before.has(c.id))
      if (!mine) throw new DataError('We could not save your request. Try again.', 400)
      const quoted = await data.projects.quoteStep(project.id, `REVISE_${shown}` as 'REVISE_1', '', [mine.id])
      await data.projects.submitStep(project.id, quoted.job.id, quoted.quote.id)
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

  const write = async (n: Num) => {
    setBusy(true)
    setError(null)
    try {
      const quoted = await data.projects.quoteStep(project.id, `CHAPTER_${n}` as 'CHAPTER_2', '')
      await data.projects.submitStep(project.id, quoted.job.id, quoted.quote.id)
      walletChanged()
      setShown(n)
      onReload()
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'This chapter could not start. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const passed = chapter ? chapter.readiness.filter((i) => i.status === 'PASS' || i.status === 'NOT_APPLICABLE').length : 0
  const status: WorkspaceStatus | null = chapter
    ? chapter.missing?.length
      ? { label: 'Some sections still to write', tone: 'warn' }
      : passed === chapter.readiness.length
        ? { label: 'Ready', tone: 'ready' }
        : { label: 'Ready with warnings', tone: 'warn' }
    : null
  const next = tabs.find((n) => !written.has(n))
  return (
    <>
      <WorkspaceHeader title={project.plan?.title ?? project.inputs.topic} meta={`Research ${concept ? 'concept paper' : 'proposal'} · ${chapter ? `${chapter.words.toLocaleString()} words` : ''}`}
        status={status} onWord={word} onPdf={pdf}
        extra={
          <Link to="?tools=1" className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-fg-muted hover:bg-surface-muted hover:text-fg">
            <Wrench className="size-4" aria-hidden /> More tools
          </Link>
        } />
      {tabs.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Chapters">
          {tabs.map((n) => (
            <button key={n} role="tab" aria-selected={shown === n} onClick={() => setShown(n)}
              className={clsx('inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors',
                shown === n ? 'bg-white text-brand-800 shadow-card ring-1 ring-brand-300' : 'text-fg-muted hover:bg-white')}>
              {NAMES[n]} {written.has(n) && <Check className="size-4 text-brand-700" aria-label="written" />}
            </button>
          ))}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="min-w-0">
          {!state?.current ? (
            <Card className="mx-auto max-w-xl p-6 text-center">
              <p className="text-lg font-semibold">{NAMES[shown]} is not written yet</p>
              <p className="mt-1 text-sm text-fg-muted">PaperAid writes it from your study’s design and confirmed sources, then checks every section.</p>
              <Button className="mt-4" loading={busy} disabled={running} onClick={() => write(shown)}>
                Write {NAMES[shown]}
              </Button>
            </Card>
          ) : !chapter ? (
            <Skeleton className="mx-auto h-[36rem] max-w-[52rem] rounded-sm" />
          ) : (
            <Paper>
              <p className="text-center text-[17px] font-semibold uppercase">{shown === CONCEPT ? 'Concept paper' : `Chapter ${['', 'One', 'Two', 'Three'][shown]}`}</p>
              <p className="text-center text-[17px] font-semibold uppercase">{chapter.title}</p>
              {chapter.sections.map((s) => (
                <section key={s.key} className="mt-6">
                  <h2 className="text-[16px] font-semibold">
                    {s.number} {s.heading}
                  </h2>
                  {s.paragraphs.map((p, i) => (
                    <Para key={i} text={p} />
                  ))}
                  {s.key === 'framework' && figure && (
                    <figure className="my-5">
                      <figcaption className="mb-2 text-sm font-semibold">Figure {shown === CONCEPT ? '1' : '1.1'}: Conceptual framework</figcaption>
                      <img src={figure} alt={project.framework} className="w-full rounded border border-[#ddd]" />
                      <p className="mt-1.5 text-xs"><i>Note.</i> Arrows show the associations this study will examine; they do not imply proven causes.</p>
                    </figure>
                  )}
                  {s.table && <DocTable caption={s.tableCaption || s.heading} rows={s.table} />}
                </section>
              ))}
              {chapter.references.length > 0 && (
                <section className="mt-8">
                  <h2 className="text-[16px] font-semibold">References</h2>
                  <ul className="mt-2 space-y-1.5">
                    {chapter.references.map((r) => (
                      <li key={r} className="pl-8 -indent-8">
                        {r}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </Paper>
          )}
        </div>
        <aside className="space-y-4 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
          <ErrorNote text={error} />
          {running && written.has(shown) && <Alert tone="info">PaperAid is working on this proposal. The new version opens here when it is ready.</Alert>}
          {next && written.has(shown) && !concept && (
            <Card className="p-5">
              <p className="text-base font-semibold">Next: {NAMES[next]}</p>
              <p className="mt-1 text-sm text-fg-muted">Written from your study’s design and confirmed sources, in the same style.</p>
              <Button className="mt-3 w-full" loading={busy} disabled={running} onClick={() => write(next)}>
                Continue to {NAMES[next]}
              </Button>
            </Card>
          )}
          {chapter && (
            <PanelSection title={`Ask for changes to ${NAMES[shown]}`}>
              <ChangeBox parts={chapter.sections.map((s) => ({ key: s.key, label: `${s.number} ${s.heading}` }))} busy={busy} running={running} onApply={apply}
                whole={shown === CONCEPT ? 'The whole concept paper' : 'The whole chapter'} />
            </PanelSection>
          )}
          {chapter && (
            <PanelSection title="What PaperAid checked" defaultOpen={false}>
              <ChecksList lines={lines(chapter.readiness)} />
            </PanelSection>
          )}
          {state && state.versions.length > 1 && (
            <PanelSection title="Versions" defaultOpen={false}>
              <Versions versions={state.versions} current={state.current}
                onPick={(v) => data.projects.setChapter(project.id, shown, v, false).then(onChange).catch(failed)} />
            </PanelSection>
          )}
          {state?.current && shown !== CONCEPT && (
            <Card className="p-5">
              {state.approved ? (
                <p className="flex items-center gap-2 text-sm font-medium text-brand-800">
                  <Check className="size-4" aria-hidden /> You approved {NAMES[shown]}.
                </p>
              ) : (
                <>
                  <p className="text-sm text-fg-muted">Happy with {NAMES[shown]} as it is? Approving it marks it final for your complete proposal; you can still ask for changes.</p>
                  <Button variant="secondary" className="mt-3 w-full" disabled={running}
                    onClick={() => data.projects.setChapter(project.id, shown, state.current, true).then(onChange).catch(failed)}>
                    Approve {NAMES[shown]}
                  </Button>
                </>
              )}
            </Card>
          )}
          {!next && !concept && <FinishCard project={project} onChange={onChange} onDownload={() => data.projects.download(project.id, true, `${stem}.docx`).catch(failed)} />}
          {!next && !concept && data.config.availability.DATALAB === 'available' && <ChapterFourCard projectId={project.id} />}
        </aside>
      </div>
    </>
  )
}
