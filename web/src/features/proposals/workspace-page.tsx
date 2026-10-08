import { clsx } from 'clsx'
import { ChartColumn, Check, Loader2, Wrench } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Alert, Card, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatTokens } from '../../lib/format'
import type { ChapterView, FrameworkStyle, Project, ReadinessItem, StepId, StepQuote, Variables } from '../../lib/proposal-types'
import type { Job } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { usePageRecord } from '../../lib/use-page-record'
import { walletChanged } from '../../lib/use-wallet'
import { StartProgress, StoppedCard } from '../start/progress'
import { ChangeBox, ChecksList, DocTable, ErrorNote, PanelSection, Paper, Para, Versions, WorkspaceHeader, type CheckLine, type WorkspaceStatus } from '../workspace/parts'
import { ProjectPage as LegacyProjectPage } from './project-page'
import { StepRunner } from './shared'

const CONCEPT = 4
type Num = 1 | 2 | 3 | 4
const NAMES: Record<number, string> = { 1: 'Chapter One', 2: 'Chapter Two', 3: 'Chapter Three', 4: 'Concept paper' }
const ESTIMATE: Record<number, string> = {
  1: 'This usually takes 10 to 20 minutes.', 2: 'This usually takes 15 to 30 minutes.', 3: 'This usually takes 10 to 25 minutes.', 4: 'This usually takes 10 to 20 minutes.',
}

/** What the proposal's running job is doing (2026-10-08: a chapter being written was shown as "Applying
 *  your changes" on the chapter before it): writing chapter n (or finishing it), or revising chapter n. */
function activity(job: Job | null): { writing: Num | null; revising: Num | null; reading: boolean } {
  const step = job?.selection.proposal ?? ''
  const n = (m: RegExpExecArray | null): Num | null => (m ? (Number(m[1]) as Num) : null)
  return { writing: step === 'CONCEPT' ? CONCEPT : n(/^CHAPTER_([1-3])$/.exec(step)), revising: n(/^REVISE_([1-4])$/.exec(step)), reading: step === 'PROFILE' }
}

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

const STYLES_ORDER: FrameworkStyle[] = ['MONO', 'GREEN', 'BLUE']
const STYLE_NAMES: Record<FrameworkStyle, string> = { MONO: 'Black and white', GREEN: 'Muted green', BLUE: 'Muted blue' }
const GROUPS: { id: keyof Variables; label: string }[] = [
  { id: 'independent', label: 'Independent' }, { id: 'dependent', label: 'Dependent' }, { id: 'intervening', label: 'Intervening' },
]

/** The conceptual framework, edited from the workspace (owner decision 2026-10-08): its style only redraws
 *  the figure; its variables change the study plan, and the sections built on them are marked for review. */
function FrameworkCard({ project, running, onChange }: { project: Project; running: boolean; onChange: (p: Project) => void }) {
  const data = useData()
  const plan = project.plan
  const [editing, setEditing] = useState(false)
  const [variables, setVariables] = useState<Variables>(() => plan?.variables ?? { independent: [], dependent: [], intervening: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!plan) return null
  const hasVariables = plan.variables.independent.length > 0 && plan.variables.dependent.length > 0
  const save = async (change: { style?: FrameworkStyle; variables?: Variables }) => {
    setBusy(true)
    setError(null)
    try {
      onChange(await data.projects.editFramework(project.id, project.planVersion, change))
      setEditing(false)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'This could not be saved. Try again.')
    } finally {
      setBusy(false)
    }
  }
  const update = (group: keyof Variables, items: string[]) => setVariables((v) => ({ ...v, [group]: items }))
  const move = (group: keyof Variables, i: number, to: keyof Variables | number) => {
    const items = [...variables[group]]
    if (typeof to === 'number') {
      if (to < 0 || to >= items.length) return
      ;[items[i], items[to]] = [items[to], items[i]]
      update(group, items)
      return
    }
    const [item] = items.splice(i, 1)
    setVariables((v) => ({ ...v, [group]: items, [to]: [...v[to], item] }))
  }
  return (
    <PanelSection title="Conceptual framework" defaultOpen={false}>
      <div className="space-y-3">
        <label className="block text-sm">
          <span className="font-medium">Style</span>
          <select className="mt-1 block h-10 w-full rounded-lg border border-line bg-white px-3 text-sm" value={project.frameworkStyle ?? 'MONO'}
            disabled={busy} onChange={(e) => save({ style: e.target.value as FrameworkStyle })}>
            {STYLES_ORDER.map((id) => <option key={id} value={id}>{STYLE_NAMES[id]}</option>)}
          </select>
        </label>
        {hasVariables && !editing && (
          <Button variant="secondary" size="sm" disabled={running} onClick={() => setEditing(true)}>Edit the variables</Button>
        )}
        {editing && (
          <div className="space-y-4">
            {GROUPS.map((g) => (
              <div key={g.id} className="space-y-2">
                <p className="text-sm font-semibold">{g.label}</p>
                {variables[g.id].map((item, i) => (
                  <div key={i} className="space-y-1 rounded-lg border border-line p-2">
                    <input aria-label={`${g.label} variable ${i + 1}`} className="h-9 w-full rounded-md border border-line px-2 text-sm" maxLength={300} value={item}
                      onChange={(e) => update(g.id, variables[g.id].map((x, j) => (j === i ? e.target.value : x)))} />
                    <div className="flex flex-wrap items-center gap-1 text-xs">
                      <button className="rounded px-1.5 py-0.5 hover:bg-surface-muted" onClick={() => move(g.id, i, i - 1)} aria-label="Move up">Up</button>
                      <button className="rounded px-1.5 py-0.5 hover:bg-surface-muted" onClick={() => move(g.id, i, i + 1)} aria-label="Move down">Down</button>
                      <select className="rounded border border-line px-1 py-0.5" value="" aria-label="Move to another group"
                        onChange={(e) => e.target.value && move(g.id, i, e.target.value as keyof Variables)}>
                        <option value="">Move to…</option>
                        {GROUPS.filter((o) => o.id !== g.id).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                      </select>
                      <button className="ml-auto rounded px-1.5 py-0.5 text-red-700 hover:bg-red-50" onClick={() => update(g.id, variables[g.id].filter((_, j) => j !== i))}>
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
                <button className="text-xs font-semibold text-brand-700 hover:underline" onClick={() => update(g.id, [...variables[g.id], ''])}>
                  Add a variable
                </button>
              </div>
            ))}
            <p className="text-xs text-fg-subtle">Saving changes your study plan: the sections that rely on these variables are marked for you to review.</p>
            <div className="flex gap-2">
              <Button size="sm" loading={busy} disabled={running} onClick={() => save({ variables })}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => { setVariables(plan.variables); setEditing(false) }}>Cancel</Button>
            </div>
          </div>
        )}
        <ErrorNote text={error} />
      </div>
    </PanelSection>
  )
}

const ALIGN_REQUEST = "Revise this section to my institution's guide: follow what the guide asks of it."

/** The student's institution guide, added once a chapter is written (owner decision 2026-10-08): PaperAid
 *  reads it and restructures the written chapters to it (order, numbering, headings), keeping each earlier
 *  version. The guide's new sections and the sections it asks for differently are then written and revised
 *  as the student's own steps, each priced before it starts. */
function GuideCard({ project, number, chapter, running, onChange, onReload }: {
  project: Project; number: Num; chapter: ChapterView; running: boolean; onChange: (p: Project) => void; onReload: () => void
}) {
  const data = useData()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [quote, setQuote] = useState<StepQuote | null>(null)
  const custom = project.rulebook.startsWith('custom-')
  const toAlign = chapter.toAlign ?? []
  const labels = chapter.sections.filter((s) => toAlign.includes(s.key)).map((s) => `${s.number} ${s.heading}`)
  const missing = chapter.missing ?? []
  const wait = running ? 'PaperAid is working on this proposal. This is available when it has finished.' : undefined
  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }
  // the student's own request on the sections to align, priced alone before it starts
  const priceRevision = () => run(async () => {
    const before = new Set(project.feedback.map((c) => c.id))
    const updated = await data.projects.requestChanges(project.id, number, ALIGN_REQUEST, toAlign)
    onChange(updated)
    const mine = updated.feedback.find((c) => c.by === 'STUDENT' && !before.has(c.id))
    if (!mine) throw new DataError('We could not save your request. Try again.', 400)
    setQuote(await data.projects.quoteStep(project.id, `REVISE_${number}` as StepId, '', [mine.id]))
  })
  const startRevision = () => run(async () => {
    if (!quote) return
    await data.projects.submitStep(project.id, quote.job.id, quote.quote.id)
    setQuote(null)
    walletChanged()
    onReload()
  })
  return (
    <PanelSection title="Align with my institution's guidelines" defaultOpen={custom && (missing.length > 0 || toAlign.length > 0)}>
      <div className="space-y-3">
        {project.profileMissing ? (
          <Alert tone="warning">Your institution's structure can no longer be read. Use the standard structure under More tools to keep working.</Alert>
        ) : !custom ? (
          <>
            <p className="text-sm text-fg-muted">
              Upload your institution's research guide. PaperAid reads it and restructures your chapters to its order, numbering and headings, then
              lists what the guide adds or asks for differently. Your current version is kept.
            </p>
            <FileDropzone compact label={project.guideName ? `Replace your guide (${project.guideName})` : "Upload your institution's guide"}
              hint="Word or PDF, up to 15,000 words" accept=".docx,.pdf" disabled={busy || running}
              onFile={(file) => run(async () => onChange(await data.projects.uploadGuide(project.id, file)))} />
            {project.guideName && !project.guideRead && (
              <StepRunner key={project.guideName} projectId={project.id} step="PROFILE" label="Read my guide and align my chapters"
                description="PaperAid reads your guide for its structure and rules, then restructures what is written to it. Your current version is kept."
                disabledReason={wait} onStarted={() => onReload()} />
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-fg-muted">
              Aligned to <span className="font-medium text-fg">{project.institution}</span>'s guide{project.guideName ? ` (${project.guideName})` : ''}: its
              order, numbering and headings. Earlier versions are under Versions.
            </p>
            {project.planProblems.length > 0 && (
              <Alert tone="warning">Your guide's rules differ from your study plan: {project.planProblems.join(' ')} Change the plan under More tools.</Alert>
            )}
            {missing.length > 0 && (
              <StepRunner key={missing.join()} projectId={project.id} step={`COMPLETE_${number}` as StepId}
                label={`Write the ${missing.length === 1 ? 'section' : `${missing.length} sections`} your guide adds`}
                description={missing.join('; ')} disabledReason={wait} onStarted={() => onReload()} />
            )}
            {toAlign.length > 0 && (
              <div className="rounded-xl border border-line p-4">
                <p className="text-sm font-semibold">Revise {toAlign.length === 1 ? 'the section' : `${toAlign.length} sections`} your guide asks for differently</p>
                <p className="mt-1 text-sm text-fg-muted">{wait ?? labels.join('; ')}</p>
                {!wait && (quote ? (
                  <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm">
                    {quote.quote.lines.map((l) => (
                      <p key={l.label} className="flex justify-between gap-3">
                        <span className="text-fg-muted">{l.label}</span> <span className="font-medium whitespace-nowrap">{formatTokens(l.amount)}</span>
                      </p>
                    ))}
                    <p className="mt-2 text-xs text-fg-subtle">
                      {data.config.creditsEnabled ? 'You are charged for the work actually done, never more than this.' : 'Not charged while PaperAid is in testing.'}
                    </p>
                    <Button className="mt-3 w-full" loading={busy} onClick={startRevision}>Revise to my guide</Button>
                  </div>
                ) : (
                  <Button className="mt-3" variant="secondary" loading={busy} onClick={priceRevision}>See the price</Button>
                ))}
              </div>
            )}
            {missing.length === 0 && toAlign.length === 0 && <p className="text-sm text-fg-muted">This chapter follows your guide.</p>}
            {project.institutionNotes.length > 0 && (
              <Alert tone="info" title="Check these with your supervisor">
                <ul className="list-disc pl-5">
                  {project.institutionNotes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </Alert>
            )}
          </>
        )}
        <ErrorNote text={error} />
      </div>
    </PanelSection>
  )
}

/** What PaperAid proposed from the topic because the student left it blank at Start (owner decision
 *  2026-10-08), marked as proposed until they confirm or correct it. A correction marks the sections built
 *  on it for review; the design is changed in the plan (More tools). */
function SettingCard({ project, running, onChange }: { project: Project; running: boolean; onChange: (p: Project) => void }) {
  const data = useData()
  const plan = project.plan
  const [area, setArea] = useState(plan?.studyArea ?? '')
  const [people, setPeople] = useState(plan?.population ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!plan || !project.proposed?.length) return null
  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      onChange(await data.projects.confirmSetting(project.id, area, people, project.planVersion))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'This could not be saved. Try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="space-y-3 p-5">
      <div>
        <p className="text-base font-semibold">Confirm your study setting</p>
        <p className="mt-1 text-sm text-fg-muted">PaperAid proposed these from your topic. Check them: nothing here is treated as confirmed until you do.</p>
      </div>
      <Input label="Where the study takes place (proposed)" maxLength={200} value={area} onChange={(e) => setArea(e.target.value)} />
      <Input label="Who or what it studies (proposed)" maxLength={200} value={people} onChange={(e) => setPeople(e.target.value)} />
      {project.proposed.includes('studyType') && (
        <div className="rounded-lg bg-surface-muted p-3 text-sm">
          <p className="font-semibold">Recommended design</p>
          <p className="mt-1 text-fg-muted">{plan.design}</p>
          <p className="mt-1 text-xs text-fg-subtle">To use another design, change it in the plan under More tools.</p>
        </div>
      )}
      <Button className="w-full" loading={busy} disabled={running || !area.trim() || !people.trim()} onClick={confirm}>
        These are right
      </Button>
      <p className="text-xs text-fg-subtle">If you change them, the sections that rely on them are marked for you to review.</p>
      <ErrorNote text={error} />
    </Card>
  )
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
  const [active, setActive] = useState<Job | null>(null)
  const [stopped, setStopped] = useState<{ n: Num; message: string } | null>(null)
  const { writing, revising, reading } = activity(active)
  const writtenKey = [...written].join(',')

  // The running job, so the page can say what it is doing and open the chapter being written.
  useEffect(() => {
    let current = true
    setActive(null)
    if (!project.activeJob) return () => { current = false }
    data.getJob(project.activeJob)
      .then((job) => {
        if (!current) return
        setActive(job)
        const now = activity(job).writing
        if (now !== null && !writtenKey.split(',').includes(String(now))) setShown(now) // the same progress view as Chapter One
      })
      .catch(() => { if (current) setActive(null) }) // not readable: the page says "working on this proposal"
    return () => { current = false }
  }, [data, project.activeJob, writtenKey])

  const onWritten = useCallback((job: Job | null) => {
    walletChanged()
    const n = activity(job).writing
    if (job?.status === 'FAILED' && n !== null) setStopped({ n, message: job.failure?.userMessage ?? 'PaperAid could not finish this chapter. Nothing was charged.' })
    window.setTimeout(onReload, 1200)
  }, [onReload])

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
  }, [data, project.id, project.framework, project.planVersion, project.frameworkStyle])

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
    setStopped(null)
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
              {writing === n && !written.has(n) && <Loader2 className="size-4 animate-spin text-brand-700" aria-label="being written" />}
            </button>
          ))}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="min-w-0">
          {!state?.current && writing === shown && project.activeJob ? (
            <StartProgress key={project.activeJob} jobId={project.activeJob} phase="write" title={`Writing ${NAMES[shown]}`} estimate={ESTIMATE[shown]} onDone={onWritten} />
          ) : !state?.current && stopped?.n === shown && !running ? (
            <StoppedCard message={stopped.message} onRetry={() => write(shown)} busy={busy} error={error} />
          ) : !state?.current ? (
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
                      <p className="mt-1.5 text-xs"><i>Note.</i> {project.frameworkNote || 'Arrows show the associations this study will examine; they do not imply proven causes.'}</p>
                      <a href={figure} download={`${stem} – conceptual framework.png`} className="mt-2 inline-block text-xs font-semibold text-brand-700 hover:underline">
                        Download the figure
                      </a>
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
          {!running && state?.current && state.needsReview.length > 0 && (
            <Alert tone="warning">
              These sections no longer match your study details: {state.needsReview.join('; ')}. Ask for changes below to bring them in line.
            </Alert>
          )}
          {running && written.has(shown) && revising !== shown && (
            writing !== null && writing !== shown ? (
              <Alert tone="info" action={<Button size="sm" variant="secondary" onClick={() => setShown(writing)}>See progress</Button>}>
                PaperAid is writing {NAMES[writing]}. It opens in its tab when it is ready.
              </Alert>
            ) : reading ? (
              <Alert tone="info">PaperAid is reading your institution's guide and aligning your chapters to it. The aligned version opens here when it is ready.</Alert>
            ) : (
              <Alert tone="info">PaperAid is working on this proposal. The new version opens here when it is ready.</Alert>
            )
          )}
          {next && written.has(shown) && !concept && writing !== next && (
            <Card className="p-5">
              <p className="text-base font-semibold">Next: {NAMES[next]}</p>
              <p className="mt-1 text-sm text-fg-muted">Written from your study’s design and confirmed sources, in the same style.</p>
              <Button className="mt-3 w-full" loading={busy} disabled={running} onClick={() => write(next)}>
                Continue to {NAMES[next]}
              </Button>
            </Card>
          )}
          <SettingCard key={project.planVersion} project={project} running={running} onChange={onChange} />
          {chapter && (
            <PanelSection title={`Ask for changes to ${NAMES[shown]}`}>
              <ChangeBox parts={chapter.sections.map((s) => ({ key: s.key, label: `${s.number} ${s.heading}` }))} busy={busy} running={running} onApply={apply}
                whole={shown === CONCEPT ? 'The whole concept paper' : 'The whole chapter'}
                runningText={revising === shown ? undefined : `${writing !== null ? `PaperAid is writing ${NAMES[writing]}.` : reading ? "PaperAid is reading your institution's guide." : 'PaperAid is working on this proposal.'} You can ask for changes here when it has finished.`} />
            </PanelSection>
          )}
          {chapter && project.framework && chapter.sections.some((s) => s.key === 'framework') && (
            <FrameworkCard key={`${project.planVersion}-${project.frameworkStyle}`} project={project} running={running} onChange={onChange} />
          )}
          {chapter && shown !== CONCEPT && (
            <GuideCard project={project} number={shown} chapter={chapter} running={running} onChange={onChange} onReload={onReload} />
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
