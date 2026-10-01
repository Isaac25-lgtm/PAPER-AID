import { ArrowLeft, CheckCircle2, FileText, Quote, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Checkbox, Input, Select, TextArea } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Alert, Card, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { CitationStyle, Level, ProposalInputs, StudyType, TitlePage } from '../../lib/proposal-types'
import { START_CHOICES, type StartType } from '../../lib/start'
import { useTitle } from '../../lib/use-title'
import type { Question, ResolvedSpec, SourceRole, Variant, Work, WorkKind } from '../../lib/work-types'
import { KIND_VARIANTS, MODES, VARIANT_LABELS } from '../works/shared'

/** One Start (owner decision 2026-10-01): two short pages, then PaperAid works by itself and opens
 *  the finished document. Page 1 says what the task is; page 2 shows what PaperAid found and asks
 *  only what this document needs. Required answers say "Required" in words, not by colour alone. */
export function StartPage() {
  const { type = '' } = useParams()
  const choice = START_CHOICES.find((c) => c.id === type)
  const data = useData()
  useTitle(choice?.name ?? 'Start')
  if (!choice) return <Navigate to="/app/new" replace />
  const availability = data.config.availability[choice.service]
  if (availability !== 'available')
    return (
      <Shell title={choice.name}>
        <Alert tone="info">
          {availability === 'invite_only' ? 'This is open to invited testers while PaperAid is in testing.' : 'This is not available yet.'}
        </Alert>
      </Shell>
    )
  if (type === 'proposal' || type === 'concept-paper') return <ProposalStart concept={type === 'concept-paper'} />
  return <WorkStart type={type as StartType} />
}

function Shell({ title, step, children }: { title: string; step?: 1 | 2; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-2xl">
      <Link to="/app/new" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> All services
      </Link>
      <div className="mb-5 flex items-end justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">{title}</h1>
        {step && <p className="shrink-0 text-sm font-medium text-fg-subtle">Step {step} of 2</p>}
      </div>
      {children}
    </div>
  )
}

// --- coursework, concept notes and funding proposals ------------------------------------------------------

const KINDS: Record<string, WorkKind> = { coursework: 'COURSEWORK', 'concept-note': 'CONCEPT_NOTE', funding: 'FUNDING_PROPOSAL' }
const TITLES: Record<WorkKind, [string, string]> = {
  COURSEWORK: ['What is your coursework?', 'A few details'],
  CONCEPT_NOTE: ['Your concept note', 'A few details'],
  FUNDING_PROPOSAL: ['Your funding proposal', 'A few details'],
}
/** Questions that decide the document, asked as required on page 2 (owner decision 2026-10-01). */
const MUST_ANSWER: Record<WorkKind, string[]> = {
  COURSEWORK: ['word_limit', 'level', 'citation_style', 'ai_policy'],
  CONCEPT_NOTE: ['applicant', 'geography', 'duration_months', 'currency'],
  FUNDING_PROPOSAL: ['applicant', 'geography', 'amount_requested', 'duration_months', 'currency'],
}
const COVER: [string, string][] = [
  ['cover:name', 'Your name'],
  ['cover:reg', 'Registration number'],
  ['cover:course', 'Course'],
  ['cover:lecturer', 'Lecturer'],
  ['cover:institution', 'Institution'],
  ['cover:due', 'Date'],
]

interface Upload {
  file: File
  role: SourceRole
}

function WorkStart({ type }: { type: StartType }) {
  const kind = KINDS[type]
  const data = useData()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [work, setWork] = useState<Work | null>(null)
  const [loading, setLoading] = useState(Boolean(params.get('work')))
  useEffect(() => {
    const id = params.get('work') // back from page 2, or a reload: continue the same work
    if (!id) return
    data.works.get(id).then((w) => setWork(w)).finally(() => setLoading(false))
  }, [data, params])
  if (loading) return <Skeleton className="mx-auto h-96 max-w-2xl rounded-2xl" />
  if (!work)
    return (
      <WorkPageOne
        kind={kind}
        onCreated={(w) => {
          setWork(w)
          navigate(`?work=${w.id}`, { replace: true })
        }}
      />
    )
  return <WorkPageTwo work={work} onChange={setWork} />
}

function WorkPageOne({ kind, onCreated }: { kind: WorkKind; onCreated: (w: Work) => void }) {
  const data = useData()
  const coursework = kind === 'COURSEWORK'
  const variants = KIND_VARIANTS[kind]
  const [variant, setVariant] = useState<Variant>(variants[0])
  const [mode, setMode] = useState(MODES[kind][1]?.id ?? MODES[kind][0]?.id ?? '')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [proposal, setProposal] = useState('')
  const [pasted, setPasted] = useState('')
  const [uploads, setUploads] = useState<Upload[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tried, setTried] = useState(false)
  const needsCall = !coursework
  const problems = {
    description: description.trim().length < 15 ? (coursework ? 'Paste your question to continue.' : 'Describe the problem in a sentence or two.') : null,
    title: !coursework && title.trim().length < 3 ? 'Give your project a short title.' : null,
    proposal: !coursework && proposal.trim().length < 15 ? 'Say what you propose to do, in a sentence or two.' : null,
    call: needsCall && !uploads.some((u) => u.role === 'CALL') && pasted.trim().split(/\s+/).length < 10 ? 'Upload or paste the call or the funder’s guidelines.' : null,
  }
  const ok = !problems.description && !problems.title && !problems.call && !problems.proposal

  const create = async () => {
    setTried(true)
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      const name = title.trim() || description.trim().split(/\s+/).slice(0, 12).join(' ')
      const answers: Record<string, string> = coursework ? {} : { problem: description.trim(), intervention: proposal.trim() }
      let w = await data.works.create(kind, variant, coursework ? '' : mode, { title: name.slice(0, 300), description: description.trim(), answers, experience: '' }, 'APA7')
      for (const u of uploads) w = await data.works.uploadSource(w.id, u.role, u.file)
      if (pasted.trim()) w = await data.works.pasteSource(w.id, 'CALL', 'The call (pasted)', pasted.trim())
      if (w.sources.length) w = await data.works.read(w.id)
      onCreated(w)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start this. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const add = (role: SourceRole) => (file: File) => setUploads((u) => [...u, { file, role }])
  return (
    <Shell title={TITLES[kind][0]} step={1}>
      <Card className="space-y-5 p-5 sm:p-6">
        <div>
          <p className="mb-2 text-sm font-medium text-fg">
            Type <span className="ml-1 text-xs font-semibold text-red-700"><span aria-hidden>*</span> Required</span>
          </p>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Type">
            {variants.map((v) => (
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={variant === v}
                onClick={() => setVariant(v)}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand-600 ${
                  variant === v ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-line-strong bg-white text-fg-muted hover:border-brand-300'
                }`}
              >
                {VARIANT_LABELS[v]}
              </button>
            ))}
          </div>
        </div>
        {!coursework && (
          <Input label="Project title" required value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} error={tried ? problems.title : null} />
        )}
        <TextArea
          label={coursework ? 'Your question or title' : 'The problem, and who it affects'}
          required
          rows={coursework ? 5 : 4}
          maxLength={8000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          hint={coursework ? 'Paste it exactly as your lecturer wrote it, every part of it.' : 'Your own words are enough. PaperAid finds the evidence.'}
          error={tried ? problems.description : null}
        />
        {!coursework && (
          <TextArea label="What you propose to do about it" required rows={3} maxLength={3000} value={proposal} onChange={(e) => setProposal(e.target.value)}
            hint="The activities, and the change they will bring." error={tried ? problems.proposal : null} />
        )}
        {coursework ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <FileDropzone compact label="Brief (optional)" hint="Word or PDF" accept=".docx,.pdf" onFile={add('BRIEF')} disabled={busy} />
            <FileDropzone compact label="Marking rubric (optional)" hint="Word or PDF" accept=".docx,.pdf" onFile={add('RUBRIC')} disabled={busy} />
            <FileDropzone compact label="Set readings (optional)" hint="Word or PDF" accept=".docx,.pdf" onFile={add('READING')} disabled={busy} />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <FileDropzone compact label="The call or funder’s guidelines" hint="Word or PDF" accept=".docx,.pdf" onFile={add('CALL')} disabled={busy} />
              <FileDropzone compact label="Their template (optional)" hint="Word or PDF" accept=".docx,.pdf" onFile={add('TEMPLATE')} disabled={busy} />
            </div>
            <TextArea label="Or paste the call’s text" rows={3} maxLength={60000} value={pasted} onChange={(e) => setPasted(e.target.value)} error={tried ? problems.call : null} />
            {MODES[kind].length > 0 && (
              <Select label="Length" value={mode} onChange={(e) => setMode(e.target.value)} hint="The call’s own limit always replaces this.">
                {MODES[kind].map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </Select>
            )}
          </div>
        )}
        {uploads.length > 0 && (
          <ul className="space-y-1.5">
            {uploads.map((u, i) => (
              <li key={`${u.file.name}-${i}`} className="flex items-center gap-2 rounded-lg bg-surface-subtle px-3 py-2 text-sm">
                <FileText className="size-4 text-fg-subtle" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{u.file.name}</span>
                <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label={`Remove ${u.file.name}`} onClick={() => setUploads((x) => x.filter((_, j) => j !== i))}>
                  <X className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end">
          <Button size="lg" loading={busy} onClick={create}>
            {busy ? (uploads.length || pasted ? 'Reading your documents…' : 'Saving…') : 'Continue'}
          </Button>
        </div>
      </Card>
    </Shell>
  )
}

function WorkPageTwo({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const navigate = useNavigate()
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [confirmed, setConfirmed] = useState(false)
  const [aiNote, setAiNote] = useState(work.aiNote)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tried, setTried] = useState(false)
  const reading = work.needsRead || Boolean(work.activeJob)

  // PaperAid is still reading the documents: check again until it has finished.
  useEffect(() => {
    if (!reading) return
    const timer = window.setInterval(() => {
      data.works.get(work.id).then((w) => w && onChange(w))
    }, 2500)
    return () => window.clearInterval(timer)
  }, [data, work.id, reading, onChange])

  if (reading)
    return (
      <Shell title="Reading your documents" step={2}>
        <Card className="space-y-3 p-6">
          <p className="text-sm text-fg-muted">PaperAid is reading what you added, so it can fill in what it finds. This usually takes under a minute.</p>
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </Card>
      </Shell>
    )
  const spec = work.spec
  if (!spec) return <Alert tone="info">PaperAid is working out the requirements.</Alert>
  const must = new Set(MUST_ANSWER[work.kind])
  const value = (id: string) => answers[id] ?? work.inputs.answers[id] ?? ''
  const skippable = (q: Question) => q.gate === 'ASK_ONCE' && !must.has(q.id)
  const shown = spec.questions.filter((q) => q.id !== 'task' && q.id !== 'confirm:all' && (!q.answered || must.has(q.id) || q.id in answers || q.id.startsWith('eligible:')))
  const required = (q: Question) => q.gate === 'BLOCK' || must.has(q.id)
  const missing = shown.filter((q) => required(q) && !value(q.id) && !(q.answered && must.has(q.id)))
  const confirmAll = spec.questions.some((q) => q.id === 'confirm:all' && !q.answered)
  const found = spec.requirements.filter((r) => r.authority === 'EXTERNAL_MANDATORY' && r.quote)

  const start = async () => {
    setTried(true)
    if (missing.length || (confirmAll && !confirmed)) return
    setBusy(true)
    setError(null)
    try {
      const given = { ...Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim())), ...(confirmAll ? { 'confirm:all': 'yes' } : {}) }
      const answered = await data.works.answer(work.id, given, work.specVersion, true)
      onChange(answered)
      if (work.kind === 'COURSEWORK' && answered.spec?.aiPolicy !== 'BANNED' && aiNote !== answered.aiNote) await data.works.setAiNote(work.id, aiNote)
      await data.works.start(work.id)
      navigate(`/app/works/${work.id}`)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start. Try again.')
      const fresh = await data.works.get(work.id).catch(() => null)
      if (fresh) onChange(fresh)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title={TITLES[work.kind][1]} step={2}>
      <div className="space-y-5">
        {found.length > 0 && (
          <Card className="p-5">
            <p className="text-base font-semibold">What PaperAid found in your documents</p>
            <ul className="mt-3 space-y-2.5">
              {found.slice(0, 12).map((r) => (
                <li key={r.id} className="text-sm">
                  <p className="flex items-start gap-2 font-medium text-fg">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-700" aria-hidden /> {r.label}: {r.value}
                  </p>
                  <p className="mt-0.5 ml-6 flex gap-1.5 text-xs text-fg-muted">
                    <Quote className="size-3 shrink-0" aria-hidden /> “{r.quote}”
                  </p>
                </li>
              ))}
            </ul>
            {confirmAll && (
              <Checkbox className="mt-4" required checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}
                label={<span className="font-medium text-fg">These are right <span className="text-xs font-semibold text-red-700"><span aria-hidden>*</span> Required</span></span>} />
            )}
            {tried && confirmAll && !confirmed && <p className="mt-1.5 text-xs font-medium text-red-600">Check what PaperAid found, then tick to confirm it.</p>}
          </Card>
        )}
        <Card className="space-y-4 p-5 sm:p-6">
          {shown.filter(required).length === 0 && <p className="text-sm text-fg-muted">PaperAid has everything it needs. Add more below if you like.</p>}
          {shown.filter(required).map((q) => (
            <Answer key={q.id} spec={spec} question={q} required value={value(q.id)} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
              error={tried && !value(q.id) && !(q.answered && must.has(q.id)) ? 'This is needed to write your document.' : null} skippable={false} />
          ))}
        </Card>
        {shown.some((q) => !required(q)) && (
          <details className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <summary className="cursor-pointer text-base font-semibold">More details (optional)</summary>
            <p className="mt-1 text-sm text-fg-muted">PaperAid uses sensible defaults for anything you leave, and says so in your document where it matters.</p>
            <div className="mt-4 space-y-4">
              {shown.filter((q) => !required(q)).map((q) => (
                <Answer key={q.id} spec={spec} question={q} required={false} value={value(q.id)} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} error={null} skippable={skippable(q)} />
              ))}
            </div>
          </details>
        )}
        {work.kind === 'COURSEWORK' && ['', 'NOT_MENTIONED'].includes(value('ai_policy')) && spec.aiPolicy !== 'BANNED' && (
          <Card className="p-5">
            <Checkbox checked={aiNote} onChange={(e) => setAiNote(e.target.checked)}
              label={<span>Add a note on the last page: “This document was drafted by an AI-assisted third party.” Your brief does not say whether AI tools are allowed, so this is on unless you untick it.</span>} />
          </Card>
        )}
        {work.kind === 'COURSEWORK' && (
          <details className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <summary className="cursor-pointer text-base font-semibold">Cover page details (optional)</summary>
            <p className="mt-1 text-sm text-fg-muted">Printed under the title only. Never sent to an AI model or a search.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {COVER.map(([id, label]) => (
                <Input key={id} label={label} maxLength={150} value={value(id)} onChange={(e) => setAnswers((a) => ({ ...a, [id]: e.target.value }))} />
              ))}
            </div>
          </details>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex items-center justify-between gap-3">
          <Link to="/app/new" className="text-sm font-medium text-fg-muted hover:text-fg">
            Cancel
          </Link>
          <Button size="lg" loading={busy} onClick={start}>
            Start
          </Button>
        </div>
      </div>
    </Shell>
  )
}

/** Choices in the student's words, never the codes behind them. */
const CHOICE_LABELS: Record<string, string> = {
  FIRST_YEAR_UG: 'First-year undergraduate', LATER_UG: 'Later undergraduate (year 2 and above)', POSTGRADUATE: 'Postgraduate (Master’s or PhD)',
  APA7: 'APA 7th edition', APA6: 'APA 6th edition', HARVARD: 'Harvard',
  NOT_MENTIONED: 'It does not say', BANNED: 'AI tools are not allowed', ALLOWED_WITH_DISCLOSURE: 'Allowed if I say I used them', ALLOWED: 'AI tools are allowed',
  USD: 'US dollars (USD)', EUR: 'Euros (EUR)', GBP: 'Pounds (GBP)', UGX: 'Uganda shillings (UGX)', KES: 'Kenya shillings (KES)', TZS: 'Tanzania shillings (TZS)',
  yes: 'Yes', no: 'No',
}

const NUMBER_HINTS: Record<string, string> = { word_limit: 'For example 2,000.', duration_months: 'In months, for example 12.', amount_requested: 'The amount you will ask for.' }

function Answer({ spec, question: q, value, onChange, required, error, skippable }: {
  spec: ResolvedSpec; question: Question; value: string; onChange: (v: string) => void; required: boolean; error: string | null; skippable: boolean
}) {
  const fallback = skippable && q.fallback ? `If you leave it: ${q.fallback}` : ''
  const hint = [q.help, NUMBER_HINTS[q.id], fallback].filter(Boolean).join(' ')
  const found = q.answered && !value ? 'PaperAid found this in your documents.' : ''
  if (q.kind === 'CHOICE' || q.kind === 'BOOL') {
    const choices = q.kind === 'BOOL' ? ['yes', 'no'] : q.choices
    const label = (c: string) => {
      if (q.id.startsWith('conflict:')) {
        const r = spec.requirements.find((x) => x.id === c)
        return r ? `${r.value} (${r.source})` : c
      }
      return CHOICE_LABELS[c] ?? c.replace(/_/g, ' ').toLowerCase().replace(/^./, (x) => x.toUpperCase())
    }
    return (
      <div>
        <Select label={q.label} required={required} value={value} hint={found || hint || undefined} onChange={(e) => onChange(e.target.value)} aria-invalid={error ? true : undefined}>
          <option value="">{q.answered ? 'Keep what PaperAid found' : 'Choose…'}</option>
          {choices.map((c) => (
            <option key={c} value={c}>
              {label(c)}
            </option>
          ))}
        </Select>
        {error && <p className="mt-1.5 text-xs font-medium text-red-600">{error}</p>}
        {q.id === 'ai_policy' && value === 'BANNED' && (
          <p className="mt-1.5 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-950">
            Your document will end with: “This document was drafted by an AI-assisted third party.” This cannot be removed.
          </p>
        )}
      </div>
    )
  }
  if (q.kind === 'LONG')
    return <TextArea label={q.label} required={required} hint={found || hint || undefined} rows={3} maxLength={3000} value={value} onChange={(e) => onChange(e.target.value)} error={error} />
  return (
    <Input label={q.label} required={required} hint={found || hint || undefined} inputMode={q.kind === 'NUMBER' ? 'decimal' : undefined} value={value}
      placeholder={q.answered ? 'Found in your documents' : undefined} onChange={(e) => onChange(e.target.value)} error={error} />
  )
}

// --- research proposals and academic concept papers -------------------------------------------------------

const LEVELS: Record<Level, string> = { BACHELORS: "Bachelor's", PGD: 'Postgraduate diploma', MASTERS: "Master's", PHD: 'PhD' }
const DESIGNS: Record<StudyType, string> = {
  QUANTITATIVE: 'Quantitative (for example a cross-sectional survey)',
  QUALITATIVE: 'Qualitative (interviews or focus groups)',
  MIXED: 'Mixed methods',
  SECONDARY: 'Secondary data',
  NON_EMPIRICAL: 'Non-empirical (desk review or theory)',
}

/** A study design suggested from the title's wording (the student confirms or changes it). */
function suggestDesign(topic: string): StudyType | null {
  const t = topic.toLowerCase()
  if (/\b(experience|perception|lived|explor|views|meaning)/.test(t)) return 'QUALITATIVE'
  if (/\b(factor|associat|prevalence|proportion|determinant|uptake|level of|effect of|relationship)/.test(t)) return 'QUANTITATIVE'
  return null
}

function ProposalStart({ concept }: { concept: boolean }) {
  const data = useData()
  const navigate = useNavigate()
  const [page, setPage] = useState<1 | 2>(1)
  const [inputs, setInputs] = useState<ProposalInputs>({
    topic: '', level: 'MASTERS', programme: '', faculty: '', studyArea: '', population: '', studyType: null, notes: '',
    populationSize: null, populationSource: '', expectedParticipants: null,
  })
  const [cover, setCover] = useState<TitlePage>({ studentName: '', regNumber: '', supervisor: '', submissionDate: '' })
  const [citation, setCitation] = useState<CitationStyle>('APA6')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tried, setTried] = useState(false)
  const set = (patch: Partial<ProposalInputs>) => setInputs((i) => ({ ...i, ...patch }))
  const title = concept ? 'Your academic concept paper' : 'Your research proposal'
  const pageOneProblem = inputs.topic.trim().length < 10 ? 'Give your working title or topic (at least a few words).' : null
  const pageTwo = {
    studyArea: !inputs.studyArea.trim() ? 'Say where the study will take place.' : null,
    population: !inputs.population.trim() ? 'Say who you will study.' : null,
    name: !cover.studentName.trim() ? 'Your name goes on the title page.' : null,
    reg: !cover.regNumber.trim() ? 'Your registration number goes on the title page.' : null,
    faculty: !inputs.faculty.trim() ? 'Your faculty or school goes on the title page.' : null,
  }

  const start = async () => {
    setTried(true)
    if (Object.values(pageTwo).some(Boolean)) return
    setBusy(true)
    setError(null)
    try {
      const project = await data.projects.create({ ...inputs, studyType: inputs.studyType ?? suggestDesign(inputs.topic) }, cover, citation, concept ? 'CONCEPT' : 'FULL')
      await data.projects.start(project.id)
      navigate(`/app/projects/${project.id}`)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not start. Try again.')
    } finally {
      setBusy(false)
    }
  }

  if (page === 1)
    return (
      <Shell title={title} step={1}>
        <Card className="space-y-5 p-5 sm:p-6">
          <TextArea label="Working title or topic" required rows={3} maxLength={300} value={inputs.topic} onChange={(e) => set({ topic: e.target.value })}
            hint="For example: Factors associated with malaria vaccine uptake among children aged 6–24 months in Lira District." error={tried ? pageOneProblem : null} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Level" required value={inputs.level} onChange={(e) => set({ level: e.target.value as Level })}>
              {Object.entries(LEVELS).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </Select>
            <Input label="Programme (optional)" maxLength={150} value={inputs.programme} onChange={(e) => set({ programme: e.target.value })} placeholder="e.g. Master of Public Health" />
          </div>
          <Alert tone="info">
            PaperAid writes to the standard structure (Uganda Christian University’s guide). If your university uses its own guide, you can add it from your proposal page afterwards.
          </Alert>
          <TextArea label="What you already have (optional)" rows={4} maxLength={4000} value={inputs.notes} onChange={(e) => set({ notes: e.target.value })}
            hint="A concept summary, your supervisor’s guidance, decisions already made." />
          <div className="flex justify-end">
            <Button size="lg" onClick={() => {
              setTried(true)
              if (pageOneProblem) return
              setTried(false)
              set({ studyType: inputs.studyType ?? suggestDesign(inputs.topic) })
              setPage(2)
            }}>
              Continue
            </Button>
          </div>
        </Card>
      </Shell>
    )

  const suggested = suggestDesign(inputs.topic)
  return (
    <Shell title="About your study" step={2}>
      <div className="space-y-5">
        <Card className="space-y-4 p-5 sm:p-6">
          <Input label="Where will the study take place?" required maxLength={200} value={inputs.studyArea} onChange={(e) => set({ studyArea: e.target.value })}
            placeholder="e.g. Lira District, Northern Uganda" error={tried ? pageTwo.studyArea : null} />
          <Input label="Who will you study?" required maxLength={200} value={inputs.population} onChange={(e) => set({ population: e.target.value })}
            placeholder="e.g. Children aged 6–24 months and their caregivers" error={tried ? pageTwo.population : null} />
          <Select label="Study design" required value={inputs.studyType ?? ''} onChange={(e) => set({ studyType: (e.target.value || null) as StudyType | null })}
            hint={suggested ? 'Suggested from your title. Change it if your supervisor agreed another.' : undefined}>
            <option value="">Let PaperAid propose one</option>
            {Object.entries(DESIGNS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </Select>
          <details className="rounded-xl border border-line p-4">
            <summary className="cursor-pointer text-sm font-semibold">Sample size (optional): PaperAid calculates it</summary>
            <p className="mt-2 text-xs text-fg-muted">
              Give only figures you have. If you leave these empty, PaperAid uses the standard settings (95% confidence, 5% margin, 50% proportion) and says so in the chapter.
            </p>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Input label="Population size (if known)" type="number" min={1} value={inputs.populationSize ?? ''} onChange={(e) => set({ populationSize: e.target.value ? Number(e.target.value) : null })} />
              <Input label="Where that figure comes from" maxLength={300} value={inputs.populationSource} onChange={(e) => set({ populationSource: e.target.value })} placeholder="e.g. district records, 2025" />
            </div>
          </details>
        </Card>
        <Card className="space-y-4 p-5 sm:p-6">
          <div>
            <p className="text-base font-semibold">Title page</p>
            <p className="mt-0.5 text-sm text-fg-muted">Printed on the title page only. Never sent to an AI model or a search.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Your name" required maxLength={120} value={cover.studentName} onChange={(e) => setCover({ ...cover, studentName: e.target.value })} error={tried ? pageTwo.name : null} />
            <Input label="Registration number" required maxLength={60} value={cover.regNumber} onChange={(e) => setCover({ ...cover, regNumber: e.target.value })} error={tried ? pageTwo.reg : null} />
            <Input label="Faculty or school" required maxLength={150} value={inputs.faculty} onChange={(e) => set({ faculty: e.target.value })} error={tried ? pageTwo.faculty : null} />
            <Input label="Supervisor (optional)" maxLength={160} value={cover.supervisor} onChange={(e) => setCover({ ...cover, supervisor: e.target.value })} />
            <Input label="Submission date (optional)" maxLength={40} value={cover.submissionDate} onChange={(e) => setCover({ ...cover, submissionDate: e.target.value })} placeholder="e.g. October 2026" />
            <Select label="Referencing style" value={citation} onChange={(e) => setCitation(e.target.value as CitationStyle)}>
              <option value="APA6">APA 6th edition</option>
              <option value="APA7">APA 7th edition</option>
            </Select>
          </div>
        </Card>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex items-center justify-between gap-3">
          <button className="text-sm font-medium text-fg-muted hover:text-fg" onClick={() => setPage(1)}>
            Back
          </button>
          <Button size="lg" loading={busy} onClick={start}>
            Start
          </Button>
        </div>
      </div>
    </Shell>
  )
}
