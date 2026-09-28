import { clsx } from 'clsx'
import { ArrowRight, CheckCircle2, Circle, Download, ExternalLink, Trash2, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Select } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Dialog, Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/overlays'
import { Alert, Badge, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatDate } from '../../lib/format'
import type { ChapterView, Comparison, EvidenceItem, Project, Rulebook } from '../../lib/proposal-types'
import type { Job } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { FeedbackPanel } from './feedback-panel'
import { PlanEditor } from './plan-editor'
import { DetailsForm } from './projects-page'
import { LEVELS, ReadinessList, StepProgress, StepRunner } from './shared'

const CHAPTERS = { 1: 'General Introduction', 2: 'Literature Review', 3: 'Methodology', 4: 'Concept Paper' } as const
const CONCEPT = 4

function Progress({ project }: { project: Project }) {
  const steps = [
    { label: 'Plan', done: project.planStatus === 'APPROVED', started: project.planStatus !== 'NONE' },
    ...project.chapters.filter((c) => c.number !== CONCEPT).map((c) => ({ label: `Chapter ${c.number}`, done: c.approved, started: c.current > 0 })),
  ]
  return (
    <ol className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {steps.map((s) => (
        <li key={s.label} className={clsx('flex items-center gap-2 rounded-xl border p-3 text-sm', s.done ? 'border-brand-300 bg-brand-50' : 'border-line bg-white')}>
          {s.done ? <CheckCircle2 className="size-4 text-brand-700" aria-hidden /> : <Circle className={clsx('size-4', s.started ? 'text-amber-600' : 'text-fg-subtle')} aria-hidden />}
          <span className="font-medium">{s.label}</span>
          <span className="ml-auto text-xs text-fg-subtle">{s.done ? 'Approved' : s.started ? 'Drafted' : ''}</span>
        </li>
      ))}
    </ol>
  )
}

function ChapterPanel({ project, number, running, onStarted, onChanged }: { project: Project; number: 1 | 2 | 3 | 4; running: boolean; onStarted: (id: string) => void; onChanged: (p: Project) => void }) {
  const concept = number === CONCEPT
  const data = useData()
  const state = project.chapters.find((c) => c.number === number)!
  const [version, setVersion] = useState(state.current)
  const [chapter, setChapter] = useState<ChapterView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [against, setAgainst] = useState(0)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => setVersion(state.current), [state.current])
  useEffect(() => {
    // A version's content is shown only once it has loaded; never the previous one under its name (Codex audit M26).
    setChapter(null)
    setError(null)
    if (!version) return
    let cancelled = false
    data.projects
      .chapter(project.id, number, version)
      .then((c) => !cancelled && setChapter(c))
      .catch((e: unknown) => !cancelled && setError(e instanceof DataError ? e.message : 'We could not load this chapter.'))
    return () => {
      cancelled = true
    }
  }, [data, project.id, number, version, project.citation, project.planVersion, attempt])
  const loaded = chapter?.version === version

  useEffect(() => {
    setComparison(null)
    if (!against || !version || against === version) return
    let cancelled = false
    data.projects
      .compare(project.id, number, Math.min(against, version), Math.max(against, version))
      .then((c) => !cancelled && setComparison(c))
      .catch((e: unknown) => !cancelled && setError(e instanceof DataError ? e.message : 'We could not compare these versions.'))
    return () => {
      cancelled = true
    }
  }, [data, project.id, number, version, against])

  const choose = async (approved: boolean) => {
    try {
      onChanged(await data.projects.setChapter(project.id, number, version, approved))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not save that.')
    }
  }

  const planReady = project.planStatus === 'APPROVED'
  const runner = (
    <StepRunner
      projectId={project.id}
      step={concept ? 'CONCEPT' : `CHAPTER_${number as 1 | 2 | 3}`}
      label={
        concept
          ? state.current
            ? 'Write a new version of the concept paper'
            : 'Write my concept paper'
          : state.current
            ? `Write a new version of Chapter ${number}`
            : `Write Chapter ${number}: ${CHAPTERS[number]}`
      }
      description={
        concept
          ? 'A short summary of your study (about five pages) for your supervisor to approve before the proposal: written from your approved plan, with five to eight annotated references.'
          : 'PaperAid researches what the chapter needs, writes it from your approved plan and checks it thoroughly before you see it. Earlier versions are kept.'
      }
      disabledReason={running ? 'A step is running for this proposal. Wait for it to finish.' : planReady ? undefined : 'Approve your plan first: it is written from it.'}
      onStarted={onStarted}
    />
  )
  if (!state.current) return runner
  const comments = project.feedback.filter((c) => c.status === 'OPEN' && c.chapter === number && c.sections.length)
  const reviser = !concept && comments.length > 0 && (
    <StepRunner
      projectId={project.id}
      step={`REVISE_${number as 1 | 2 | 3}`}
      label={`Revise from your supervisor's comments (${comments.length})`}
      description="PaperAid revises only the sections these comments are on and checks them again. Every other section stays exactly as it is, and the current version is kept."
      disabledReason={running ? 'A step is running for this proposal. Wait for it to finish.' : planReady ? undefined : 'Approve your plan first.'}
      onStarted={onStarted}
    />
  )
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <Select label="Version" className="w-72" value={version} onChange={(e) => setVersion(Number(e.target.value))}>
            {[...state.versions].reverse().map((v) => (
              <option key={v.version} value={v.version}>
                Version {v.version} · {formatDate(v.createdAt)}
                {v.version === state.current ? ' (current)' : ''}
              </option>
            ))}
          </Select>
          {state.versions.length > 1 && (
            <Select label="Compare with" className="w-56" value={against} onChange={(e) => setAgainst(Number(e.target.value))}>
              <option value={0}>No comparison</option>
              {[...state.versions].reverse().filter((v) => v.version !== version).map((v) => (
                <option key={v.version} value={v.version}>
                  Version {v.version}
                </option>
              ))}
            </Select>
          )}
          {concept && (
            <Button
              variant="secondary"
              onClick={() =>
                data.projects
                  .downloadConcept(project.id, `${(project.plan?.title ?? 'Proposal').slice(0, 70)} – concept paper.docx`)
                  .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not prepare the concept paper.'))
              }
            >
              <Download className="size-4" aria-hidden /> Concept paper (Word)
            </Button>
          )}
          {version !== state.current ? (
            <Button variant="secondary" disabled={!loaded} onClick={() => choose(false)}>
              Use this version
            </Button>
          ) : state.approved ? (
            <Badge tone="brand">Approved</Badge>
          ) : (
            <Button disabled={!loaded} onClick={() => choose(true)}>
              {concept ? 'Approve the concept paper' : 'Approve this chapter'}
            </Button>
          )}
        </div>
        {error && (
          <Alert
            tone="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </Button>
            }
          >
            {error}
          </Alert>
        )}
        {version === state.current && state.needsReview.length > 0 && (
          <Alert tone="warning" title="Written from decisions you have since changed">
            These sections no longer match your plan: {state.needsReview.join('; ')}. Write a new version to bring them in line.
          </Alert>
        )}
        {chapter?.warnings.map((w) => (
          <Alert key={w} tone="warning">
            {w}
          </Alert>
        ))}
        {comparison ? (
          <CompareView comparison={comparison} />
        ) : !chapter ? (
          error ? null : <Skeleton className="h-96 rounded-2xl" />
        ) : (
          <Card className="p-5 sm:p-8">
            {!concept && <p className="text-center text-xs font-semibold tracking-wide text-fg-subtle uppercase">Chapter {number}</p>}
            <h2 className="text-center text-xl font-bold">{chapter.title}</h2>
            <p className="mt-1 text-center text-xs text-fg-subtle">{chapter.words.toLocaleString()} words · written from plan version {chapter.planVersion}</p>
            {chapter.sections.map((s) => (
              <section key={s.number} className="mt-6">
                <h3 className="flex items-center gap-2 font-semibold">
                  {s.number} {s.heading}
                  {s.needsReview && <Badge tone="warning">Needs review</Badge>}
                </h3>
                {s.paragraphs.map((p, i) => (
                  <p key={i} className="mt-2 text-[15px] leading-relaxed text-fg">
                    {p}
                  </p>
                ))}
                {s.key === 'framework' && chapter.framework.length > 0 && <Framework columns={chapter.framework} figure={concept ? 'Figure 1' : 'Figure 1.1'} />}
                {s.table && (
                  <div className="mt-3 overflow-x-auto">
                    {s.tableCaption && <p className="mb-1 text-sm font-semibold">{s.tableCaption}</p>}
                    <table className="w-full border-collapse text-sm">
                      <tbody>
                        {s.table.map((row, r) => (
                          <tr key={r} className={r === 0 ? 'font-semibold' : ''}>
                            {row.map((cell, c) => (
                              <td key={c} className="border border-line px-2 py-1">
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ))}
            {chapter.references.length > 0 && (
              <section className="mt-8 border-t border-line pt-4">
                <h3 className="font-semibold">{concept ? 'References' : 'References in this chapter'}</h3>
                <ul className="mt-2 space-y-1.5">
                  {chapter.references.map((r) => (
                    <li key={r} className="pl-6 -indent-6 text-sm text-fg-muted">
                      {r}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </Card>
        )}
      </div>
      <aside className="space-y-4">
        {chapter && (
          <Card className="p-4">
            <p className="mb-2 text-sm font-semibold">Readiness</p>
            <ReadinessList items={chapter.readiness} />
          </Card>
        )}
        {reviser}
        {runner}
      </aside>
    </div>
  )
}

/** Chapter One's conceptual framework, drawn from the plan's variables (the Word file has the same figure). */
function Framework({ columns, figure }: { columns: { label: string; items: string[] }[]; figure: string }) {
  return (
    <figure className="mt-4">
      <figcaption className="mb-2 text-sm font-semibold">{figure}: Conceptual framework</figcaption>
      <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
        {columns.map((c, i) => (
          <div key={c.label} className="contents">
            {i > 0 && <ArrowRight className="mx-auto size-5 shrink-0 rotate-90 text-fg-subtle sm:rotate-0" aria-hidden />}
            <div className="flex-1 rounded-lg border-2 border-fg/70 p-3">
              <p className="text-sm font-semibold">{c.label}</p>
              <ul className="mt-1 list-disc pl-5 text-sm">
                {c.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-fg-subtle">Drawn from the variables in your approved plan.</p>
    </figure>
  )
}

/** Two versions side by side in one text: what was removed struck through, what was added marked. */
function CompareView({ comparison }: { comparison: Comparison }) {
  return (
    <Card className="p-5 sm:p-8">
      <p className="text-sm text-fg-muted">
        Version {comparison.older} → version {comparison.newer}: {comparison.changed === 0 ? 'no section changed.' : `${comparison.changed} section${comparison.changed === 1 ? '' : 's'} changed.`}
      </p>
      {comparison.sections.map((s) => (
        <section key={`${s.number}-${s.heading}`} className="mt-6">
          <h3 className="flex items-center gap-2 font-semibold">
            {s.number} {s.heading}
            {s.status !== 'SAME' && <Badge tone={s.status === 'REMOVED' ? 'warning' : 'brand'}>{s.status === 'CHANGED' ? 'Changed' : s.status === 'ADDED' ? 'New' : 'Removed'}</Badge>}
          </h3>
          <p className={clsx('mt-2 text-[15px] leading-relaxed whitespace-pre-line', s.status === 'SAME' && 'text-fg-subtle')}>
            {s.pieces.map((piece, i) =>
              piece.op === 'same' ? (
                <span key={i}>{piece.text} </span>
              ) : piece.op === 'added' ? (
                <ins key={i} className="bg-brand-100 text-brand-900 no-underline">
                  {piece.text}{' '}
                </ins>
              ) : (
                <del key={i} className="bg-red-50 text-red-800">
                  {piece.text}{' '}
                </del>
              ),
            )}
          </p>
        </section>
      ))}
    </Card>
  )
}

/** The institution the proposal is written for: the default structure, or one read from the
 * student's own research guide (before any chapter is written). */
function InstitutionCard({ project, running, onStarted, onChanged }: { project: Project; running: boolean; onStarted: (id: string) => void; onChanged: (p: Project) => void }) {
  const data = useData()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const custom = project.rulebook.startsWith('custom-')
  const written = project.chapters.some((c) => c.versions.length > 0)
  const run = async (action: () => Promise<Project>) => {
    setBusy(true)
    setError(null)
    try {
      onChanged(await action())
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="space-y-3 p-5">
      <div>
        <p className="text-sm font-semibold">Your institution</p>
        <p className="mt-1 text-sm text-fg-muted">
          {custom ? (
            <>
              Written to <span className="font-medium text-fg">{project.institution}</span>&rsquo;s structure, read from your guide
              {project.guideName ? ` (${project.guideName})` : ''}.
            </>
          ) : (
            <>
              Written to the standard proposal structure: introduction, literature review and methodology. If your institution has its own research
              guide, upload it and PaperAid follows its chapters, headings and rules instead.
            </>
          )}
        </p>
      </div>
      {custom && project.institutionNotes.length > 0 && (
        <Alert tone="info" title="Check these with your supervisor">
          <ul className="list-disc pl-5">
            {project.institutionNotes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Alert>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      {written ? (
        <p className="text-xs text-fg-subtle">Your chapters follow this structure; it stays the same for this proposal.</p>
      ) : (
        <>
          <FileDropzone
            compact
            label={project.guideName ? `Replace your guide (${project.guideName})` : "Upload your institution's research guide"}
            hint="Word or PDF, up to 15,000 words"
            accept=".docx,.pdf"
            disabled={busy}
            onFile={(file) => run(() => data.projects.uploadGuide(project.id, file))}
          />
          {project.guideName && !project.guideRead && (
            <StepRunner
              key={project.guideName}
              projectId={project.id}
              step="PROFILE"
              label="Use my institution's guide"
              description="PaperAid reads your guide for its proposal structure, rules and assessment questions, and writes your proposal to them."
              disabledReason={running ? 'A step is running for this proposal. Wait for it to finish.' : undefined}
              onStarted={onStarted}
            />
          )}
          {custom && (
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => run(() => data.projects.useDefaultRulebook(project.id))}>
              Use the default structure instead
            </Button>
          )}
        </>
      )}
    </Card>
  )
}

/** Everything that stands between the proposal and a complete download, in one place. */
function ReadyPanel({ project, onDownload }: { project: Project; onDownload: (final: boolean, pdf?: boolean) => void }) {
  const data = useData()
  const [error, setError] = useState<string | null>(null)
  const open = project.feedback.filter((c) => c.status === 'OPEN').length
  const ready = project.blockers.length === 0
  return (
    <div className="max-w-3xl space-y-4">
      {error && <Alert tone="danger">{error}</Alert>}
      {ready ? (
        <Alert tone="success" title="Your proposal is complete">
          Every chapter is written and approved and the title page is filled in. Read it through once more, then download it.
        </Alert>
      ) : (
        <Card className="p-5">
          <p className="font-semibold">Before the complete proposal can be downloaded</p>
          <ul className="mt-3 space-y-2">
            {project.blockers.map((b) => (
              <li key={b} className="flex gap-2 text-sm">
                <Circle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden /> {b}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {open > 0 && (
        <Alert tone="info">
          {open === 1 ? 'One supervisor comment is' : `${open} supervisor comments are`} still to do. They do not stop the download, but your supervisor will
          look for them.
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button disabled={!ready} onClick={() => onDownload(true)}>
          <Download className="size-4" aria-hidden /> Complete proposal (Word)
        </Button>
        <Button variant="secondary" disabled={!project.chapters.some((c) => c.number !== CONCEPT && c.current)} onClick={() => onDownload(ready, true)}>
          <Download className="size-4" aria-hidden /> {ready ? 'Complete proposal (PDF)' : 'Draft (PDF)'}
        </Button>
        <Button variant="secondary" disabled={!project.chapters.some((c) => c.number !== CONCEPT && c.current)} onClick={() => onDownload(false)}>
          <Download className="size-4" aria-hidden /> Draft (Word)
        </Button>
        {project.feedback.length > 0 && (
          <Button variant="secondary" onClick={() => data.projects.downloadResponse(project.id).catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not prepare the report.'))}>
            <Download className="size-4" aria-hidden /> Response to comments
          </Button>
        )}
      </div>
    </div>
  )
}

function EvidencePanel({ projectId, count }: { projectId: string; count: number }) {
  const data = useData()
  const [items, setItems] = useState<EvidenceItem[] | null>(null)
  useEffect(() => {
    data.projects.evidence(projectId).then(setItems).catch(() => setItems([]))
  }, [data, projectId, count])
  if (!items) return <Skeleton className="h-48 rounded-2xl" />
  if (!items.length) return <p className="text-sm text-fg-muted">Evidence appears here once PaperAid has researched your plan or a chapter.</p>
  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-muted">
        Chapters cite only sources PaperAid has confirmed say what they are cited for. References are built from the
        source&rsquo;s registered details.
      </p>
      {items.map((item) => {
        const usable = item.verified && (item.support === 'SUPPORTED' || item.support === 'PARTLY_SUPPORTED')
        return (
          <Card key={item.id} className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              {usable ? <Badge tone="brand">Confirmed</Badge> : item.verified ? <Badge tone="warning">Does not support the statement</Badge> : <Badge>Found, not confirmed</Badge>}
              <span className="text-xs text-fg-subtle">
                {item.access === 'ABSTRACT' ? 'Abstract read' : item.access === 'FULL_TEXT' ? 'Page read' : 'Search snippet'} · retrieved {item.retrievedOn}
              </span>
            </div>
            <p className="mt-2 text-sm font-medium">{item.statement}</p>
            <blockquote className="mt-1 border-l-2 border-line pl-3 text-sm text-fg-muted italic">&ldquo;{item.passage}&rdquo;</blockquote>
            <a href={item.source.url} target="_blank" rel="noreferrer noopener" className="mt-2 inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
              {item.source.title} {item.source.year && `(${item.source.year})`} <ExternalLink className="size-3" aria-hidden />
            </a>
          </Card>
        )
      })}
    </div>
  )
}

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const data = useData()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null | undefined>(undefined)
  const [rulebook, setRulebook] = useState<Rulebook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState<string | null>(null)
  // A step started by an action (Chapter One after the plan is approved) appears as it starts.
  useEffect(() => {
    if (project?.activeJob && !running) setRunning(project.activeJob)
  }, [project?.activeJob, running])
  const [finished, setFinished] = useState<Job | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useTitle(project?.plan?.title ?? project?.inputs.topic ?? 'Proposal')

  const load = useCallback(() => {
    data.projects
      .get(projectId)
      .then((p) => {
        setProject(p)
        setRunning(p?.activeJob ?? null)
      })
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load this proposal.'))
  }, [data, projectId])
  useEffect(load, [load])
  useEffect(() => {
    data.projects.rulebook().then(setRulebook).catch(() => setRulebook(null))
  }, [data])

  const onDone = useCallback(
    (job: Job | null) => {
      setRunning(null)
      setFinished(job)
      load()
    },
    [load],
  )

  const download = async (final: boolean, pdf = false) => {
    if (!project) return
    setError(null)
    try {
      const name = `${(project.plan?.title ?? 'Proposal').slice(0, 80)}${final ? '' : ' – draft'}.${pdf ? 'pdf' : 'docx'}`
      await (pdf ? data.projects.downloadPdf(project.id, final, name) : data.projects.download(project.id, final, name))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not prepare the document.')
    }
  }

  if (project === undefined)
    return error ? (
      <Alert
        tone="danger"
        title="We could not load this proposal"
        action={
          <Button size="sm" variant="secondary" onClick={() => (setError(null), load())}>
            Try again
          </Button>
        }
      >
        {error}
      </Alert>
    ) : (
      <Skeleton className="h-96 rounded-2xl" />
    )
  if (project === null) return <Alert tone="warning">This proposal no longer exists.</Alert>
  const hasChapter = project.chapters.some((c) => c.number !== CONCEPT && c.current)

  return (
    <>
      <PageHeader
        title={project.plan?.title ?? project.inputs.topic}
        description={
          <>
            {LEVELS[project.inputs.level]} · {project.citation === 'APA6' ? 'APA 6' : 'APA 7'} · kept until {formatDate(project.expiresAt)} unless you
            work on it again
          </>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={!hasChapter} onClick={() => download(false)}>
              <Download className="size-4" aria-hidden /> Draft (Word)
            </Button>
            <Button disabled={!hasChapter} onClick={() => download(true)}>
              <Download className="size-4" aria-hidden /> Complete proposal
            </Button>
            <Button variant="ghost" aria-label="Delete proposal" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-4" aria-hidden />
            </Button>
          </div>
        }
      />
      {error && (
        <Alert tone="danger" className="mb-5">
          {error}
        </Alert>
      )}
      {running && (
        <div className="mb-5">
          <StepProgress jobId={running} onDone={onDone} />
        </div>
      )}
      {finished && !running && (
        <Alert tone={finished.status === 'COMPLETED' ? (finished.outcome === 'PARTIAL' ? 'warning' : 'success') : 'danger'} className="mb-5" title={finished.status === 'COMPLETED' ? 'Step finished' : 'The step did not finish'}>
          {finished.status === 'COMPLETED' ? (finished.warnings.length ? finished.warnings.join(' ') : 'Saved to your proposal.') : (finished.failure?.userMessage ?? 'Nothing was charged.')}
        </Alert>
      )}
      {project.notice && (
        <Alert tone="warning" className="mb-5">
          {project.notice}
        </Alert>
      )}
      <Progress project={project} />
      <Tabs defaultValue="plan">
        <TabsList className="mb-5">
          <TabsTrigger value="plan">Plan</TabsTrigger>
          <TabsTrigger value="concept">Concept paper</TabsTrigger>
          {project.chapters.filter((c) => c.number !== CONCEPT).map((c) => (
            <TabsTrigger key={c.number} value={`c${c.number}`}>
              Chapter {c.number}
              {c.needsReview.length > 0 && <TriangleAlert className="ml-1 size-3.5 text-amber-600" aria-label="needs review" />}
            </TabsTrigger>
          ))}
          <TabsTrigger value="feedback">
            Supervisor feedback
            {project.feedback.some((c) => c.status === 'OPEN') && ` (${project.feedback.filter((c) => c.status === 'OPEN').length})`}
          </TabsTrigger>
          <TabsTrigger value="evidence">Evidence ({project.evidenceCount})</TabsTrigger>
          <TabsTrigger value="ready">
            Ready?
            {project.blockers.length === 0 && <CheckCircle2 className="ml-1 size-3.5 text-brand-700" aria-label="ready" />}
          </TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
        </TabsList>
        <TabsContent value="plan" className="space-y-5">
          {project.candidatePlan && (
            <Alert
              tone="info"
              title="PaperAid finished a plan while you were editing yours"
              action={
                <div className="flex gap-2">
                  <Button size="sm" onClick={async () => setProject(await data.projects.takeCandidate(project.id, true))}>
                    Use the new plan
                  </Button>
                  <Button size="sm" variant="secondary" onClick={async () => setProject(await data.projects.takeCandidate(project.id, false))}>
                    Keep mine
                  </Button>
                </div>
              }
            >
              Its title: &ldquo;{project.candidatePlan.title}&rdquo;. Your own edits were kept.
            </Alert>
          )}
          {project.plan && <PlanEditor project={project} onSaved={setProject} />}
          <StepRunner
            projectId={project.id}
            step="PLAN"
            label={project.plan ? 'Draft a new plan' : 'Draft my plan, then Chapter One'}
            description={
              project.plan
                ? 'PaperAid researches your topic again and drafts a fresh plan. You edit and approve it before any chapter is written.'
                : 'PaperAid researches your topic and drafts a plan for your study: problem, objectives, questions, design and methods. You edit and approve it, and Chapter One starts as soon as you do.'
            }
            disabledReason={running ? 'A step is running for this proposal. Wait for it to finish.' : undefined}
            onStarted={setRunning}
          />
        </TabsContent>
        {([1, 2, 3, 4] as const).map((n) => (
          <TabsContent key={n} value={n === CONCEPT ? 'concept' : `c${n}`}>
            <ChapterPanel project={project} number={n} running={!!running} onStarted={setRunning} onChanged={setProject} />
          </TabsContent>
        ))}
        <TabsContent value="feedback">
          <FeedbackPanel project={project} onChanged={setProject} />
        </TabsContent>
        <TabsContent value="ready">
          <ReadyPanel project={project} onDownload={download} />
        </TabsContent>
        <TabsContent value="evidence">
          <EvidencePanel projectId={project.id} count={project.evidenceCount} />
        </TabsContent>
        <TabsContent value="details" className="max-w-3xl space-y-5">
          <InstitutionCard project={project} running={!!running} onStarted={setRunning} onChanged={setProject} />
          <DetailsForm
            key={`${project.rulebook}-${project.citation}`}
            initial={project.inputs}
            titlePage={project.titlePage}
            citation={project.citation}
            rulebook={rulebook}
            submitLabel="Save details"
            onSubmit={async (inputs, titlePage, citation) => setProject(await data.projects.updateDetails(project.id, inputs, titlePage, citation))}
          />
        </TabsContent>
      </Tabs>
      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this proposal?"
        description="Its plan, every chapter version and its evidence are deleted for good."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              onClick={async () => {
                try {
                  await data.projects.remove(project.id)
                  navigate('/app/projects')
                } catch (e) {
                  setConfirmDelete(false)
                  setError(e instanceof DataError ? e.message : 'We could not delete this proposal.')
                }
              }}
            >
              Delete
            </Button>
          </>
        }
      />
    </>
  )
}
