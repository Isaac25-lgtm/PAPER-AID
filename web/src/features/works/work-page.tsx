import * as TabsPrimitive from '@radix-ui/react-tabs'
import { CheckCircle2, CircleAlert, Download, FileText, Plus, Quote, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { Button } from '../../components/ui/button'
import { Checkbox, Input, Select, TextArea } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { TabsContent, TabsList, TabsTrigger } from '../../components/ui/overlays'
import { Alert, Badge, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import type { Budget, BudgetLine, Question, ResolvedSpec, ResultsModel, SourceRole, Work, WorkDocumentView, WorkPlan } from '../../lib/work-types'
import { ReadinessList, ReviewNotice } from '../proposals/shared'
import { KIND_LABELS, ReadinessBadge, SOURCE_ROLES, VARIANT_LABELS, WorkProgress, WorkStepRunner, money } from './shared'

type Tab = 'documents' | 'understood' | 'plan' | 'results' | 'budget' | 'draft'
const SKIPPED = 'SKIPPED'
const NO_LIMIT = 'NO_LIMIT' // the brief gives no word limit: PaperAid never invents one

function useAction(onDone: (work: Work) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (action: () => Promise<Work>) => {
    setBusy(true)
    setError(null)
    try {
      onDone(await action())
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

/** The page for works set up before one Start (owner decision 2026-10-01), until they are written. */
export function LegacyWorkPage() {
  const { workId = '' } = useParams()
  const data = useData()
  const [work, setWork] = useState<Work | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab | null>(null)
  useTitle(work?.plan?.title ?? work?.inputs.title ?? 'Work')

  const load = useCallback(() => {
    data.works
      .get(workId)
      .then(setWork)
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'We could not load this work.'))
  }, [data, workId])
  useEffect(load, [load])
  const onStepDone = useCallback(() => load(), [load])

  if (error) return <Alert tone="danger">{error}</Alert>
  if (work === undefined) return <Skeleton className="h-64 rounded-2xl" />
  if (work === null) return <Alert tone="warning">We couldn't find this work.</Alert>

  const funding = work.kind === 'FUNDING_PROPOSAL'
  const current = tab ?? defaultTab(work)
  return (
    <>
      <PageHeader title={work.plan?.title ?? work.inputs.title} description={`${KIND_LABELS[work.kind]} · ${VARIANT_LABELS[work.variant]}`} actions={<ReadinessBadge status={work.status} />} />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <TabsPrimitive.Root value={current} onValueChange={(v) => setTab(v as Tab)}>
          <TabsList className="mb-4 flex-wrap">
            <TabsTrigger value="documents">Your documents</TabsTrigger>
            <TabsTrigger value="understood">What PaperAid understood</TabsTrigger>
            <TabsTrigger value="plan" disabled={!work.plan}>Plan</TabsTrigger>
            {funding && <TabsTrigger value="results" disabled={!work.results}>Results Model</TabsTrigger>}
            {funding && <TabsTrigger value="budget" disabled={!work.budget}>Budget</TabsTrigger>}
            <TabsTrigger value="draft" disabled={!work.documents.length}>Your draft</TabsTrigger>
          </TabsList>
          <TabsContent value="documents">
            <DocumentsPanel work={work} onChange={setWork} />
          </TabsContent>
          <TabsContent value="understood">
            <UnderstoodPanel work={work} onChange={setWork} />
          </TabsContent>
          <TabsContent value="plan">{work.plan && <PlanPanel work={work} onChange={setWork} />}</TabsContent>
          {funding && <TabsContent value="results">{work.results && <ResultsPanel work={work} onChange={setWork} />}</TabsContent>}
          {funding && <TabsContent value="budget">{work.budget && <BudgetPanel work={work} onChange={setWork} />}</TabsContent>}
          <TabsContent value="draft">{work.documents.length > 0 && <DocumentPanel work={work} onChange={setWork} onStarted={load} />}</TabsContent>
        </TabsPrimitive.Root>
        <aside className="space-y-4">
          <NextStep work={work} onStarted={load} onDone={onStepDone} onGo={setTab} />
        </aside>
      </div>
    </>
  )
}

function defaultTab(work: Work): Tab {
  if (work.documents.length) return 'draft'
  if (work.plan) return 'plan'
  if (work.needsRead || work.sources.length === 0) return work.specStatus === 'CONFIRMED' ? 'understood' : 'documents'
  return 'understood'
}

/** The one step that comes next, beside the work (owner decision 2026-09-29: one screen). */
function NextStep({ work, onStarted, onDone, onGo }: { work: Work; onStarted: () => void; onDone: () => void; onGo: (tab: Tab) => void }) {
  const spec = work.spec
  if (work.activeJob) return <WorkProgress jobId={work.activeJob} onDone={onDone} />
  const go = (tab: Tab, label: string, text: string) => (
    <Card className="p-4">
      <p className="text-sm font-semibold">{label}</p>
      <p className="mt-1 text-sm text-fg-muted">{text}</p>
      <Button className="mt-3" size="sm" variant="secondary" onClick={() => onGo(tab)}>
        Open
      </Button>
    </Card>
  )
  if (work.needsRead)
    return (
      <WorkStepRunner workId={work.id} step="READ" label="Read my documents" withNote={false} onStarted={onStarted}
        description="PaperAid reads your documents and lists every requirement with its exact words, for you to confirm." />
    )
  if (!spec || spec.gate !== 'PASS' || work.specStatus !== 'CONFIRMED')
    return go('understood', 'Check what PaperAid understood', spec?.blockers.length ? spec.blockers[0] : 'Answer the questions and confirm before PaperAid plans.')
  if (!work.plan)
    return <WorkStepRunner workId={work.id} step="PLAN" label="Make my plan" onStarted={onStarted} description="PaperAid researches the evidence and plans every section for you to edit and approve." />
  if (work.planStatus !== 'APPROVED') return go('plan', 'Review and approve your plan', 'Nothing is written until you approve it.')
  if (work.kind === 'FUNDING_PROPOSAL' && work.resultsStatus !== 'APPROVED') return go('results', 'Complete your Results Model', 'Add your baselines and targets, then approve it.')
  if (work.kind === 'FUNDING_PROPOSAL' && !(work.budget?.lines.some((l) => l.unitCost > 0) ?? false))
    return go('budget', 'Add your budget', 'Enter the quantities and unit costs. PaperAid does every sum.')
  const blocking = work.checks.filter((c) => c.status === 'BLOCKED')
  if (!work.documents.length || work.requests.every((r) => r.status !== 'OPEN'))
    return (
      <div className="space-y-3">
        {blocking.length > 0 && (
          <Alert tone="warning" title="Fix these first">
            <ul className="list-disc pl-4">
              {blocking.map((c) => (
                <li key={c.id}>
                  {c.question}: {c.note}
                </li>
              ))}
            </ul>
          </Alert>
        )}
        <WorkStepRunner workId={work.id} step="DRAFT" label={work.documents.length ? 'Write it again' : 'Write my draft'} onStarted={onStarted}
          description="PaperAid writes every section from your approved plan, checks it against every rule, and repairs what fails." />
      </div>
    )
  return <WorkStepRunner workId={work.id} step="REVISE" label="Make my changes" onStarted={onStarted} description="PaperAid revises the sections you chose, in your words, and checks them again." />
}

// --- your documents ---------------------------------------------------------------------------------

function DocumentsPanel({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const coursework = work.kind === 'COURSEWORK'
  const [role, setRole] = useState<SourceRole>(coursework ? 'BRIEF' : 'CALL')
  const [pasted, setPasted] = useState('')
  const roles: SourceRole[] = coursework ? ['BRIEF', 'RUBRIC', 'READING', 'GUIDE', 'OTHER'] : ['CALL', 'TEMPLATE', 'ADDENDUM', 'GUIDE', 'OTHER']
  return (
    <Card className="space-y-4 p-5">
      <p className="text-sm text-fg-muted">
        {coursework
          ? 'Add your assignment brief, marking rubric and any set readings. Your brief always outranks PaperAid’s defaults.'
          : 'Add the call for proposals, its template and any addendum. The call always outranks PaperAid’s defaults.'}
      </p>
      {work.sources.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {work.sources.map((s) => (
            <li key={s.id} className="flex items-center gap-3 p-3 text-sm">
              <FileText className="size-4 text-fg-subtle" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-medium">{s.name}</span>
              <Badge>{SOURCE_ROLES[s.role]}</Badge>
              <span className="text-xs text-fg-subtle">{s.words.toLocaleString()} words</span>
              <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label={`Remove ${s.name}`} onClick={() => run(() => data.works.removeSource(work.id, s.id))}>
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Select label="What is it?" value={role} onChange={(e) => setRole(e.target.value as SourceRole)}>
        {roles.map((r) => (
          <option key={r} value={r}>
            {SOURCE_ROLES[r]}
          </option>
        ))}
      </Select>
      <FileDropzone label="Upload it (Word or PDF)" hint="PaperAid keeps its text only for this work." accept=".docx,.pdf" onFile={(file) => run(() => data.works.uploadSource(work.id, role, file))} disabled={busy} compact />
      <TextArea label="Or paste its text" rows={4} value={pasted} onChange={(e) => setPasted(e.target.value)} />
      <Button size="sm" variant="secondary" loading={busy} disabled={pasted.trim().length < 10} onClick={() => run(() => data.works.pasteSource(work.id, role, SOURCE_ROLES[role], pasted)).then(() => setPasted(''))}>
        Add the pasted text
      </Button>
      {error && <Alert tone="warning">{error}</Alert>}
    </Card>
  )
}

// --- what PaperAid understood ---------------------------------------------------------------------------

function answerText(spec: ResolvedSpec, q: Question, value: string) {
  if (q.id.startsWith('conflict:')) {
    const r = spec.requirements.find((x) => x.id === value)
    return r ? `${r.value} (${r.source})` : value
  }
  return value
}

function UnderstoodPanel({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const spec = work.spec
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [touched, setTouched] = useState<string[]>([])
  const [saving, setSaving] = useState<Record<string, string>>({}) // question → "saving", "saved" or the reason it was not saved
  const [details, setDetails] = useState(work.inputs)
  useEffect(() => setDetails(work.inputs), [work.inputs])
  const version = useRef(work.specVersion)
  useEffect(() => {
    version.current = work.specVersion
  }, [work.specVersion])
  const queue = useRef<Promise<void>>(Promise.resolve())
  if (!spec) return <Alert tone="info">PaperAid is working out the requirements.</Alert>
  const value = (id: string) => answers[id] ?? work.inputs.answers[id] ?? ''
  const set = (id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v }))
  // Each answer is saved as soon as it is given (on leaving the box, or on choosing), one save after
  // another on the latest version, so none is lost or refused as stale.
  const save = (id: string, v: string) => {
    setTouched((t) => (t.includes(id) ? t : [...t, id]))
    if (v === (work.inputs.answers[id] ?? '') && !(id in answers)) return
    queue.current = queue.current.then(async () => {
      setSaving((st) => ({ ...st, [id]: 'saving' }))
      try {
        const updated = await data.works.answer(work.id, { [id]: v }, version.current)
        version.current = updated.specVersion
        onChange(updated)
        setAnswers((a) => Object.fromEntries(Object.entries(a).filter(([k]) => k !== id)))
        setSaving((st) => ({ ...st, [id]: 'saved' }))
      } catch (e) {
        setSaving((st) => ({ ...st, [id]: e instanceof DataError ? e.message : 'Not saved. Try again.' }))
      }
    })
  }
  const open = spec.questions.filter((q) => !q.answered || q.id in answers || touched.includes(q.id))
  const waiting = spec.questions.filter((q) => !q.answered && q.id !== 'experience')
  const whyNot = [
    ...(work.needsRead ? ['PaperAid has not read your latest documents yet: choose "Read my documents" first.'] : []),
    ...spec.blockers,
    ...waiting.filter((q) => q.gate === 'ASK_ONCE').map((q) => `Answer "${q.label}", or choose "Use PaperAid's defaults for the rest".`),
  ]
  const external = spec.requirements.filter((r) => r.authority === 'EXTERNAL_MANDATORY')
  const summary: [string, string][] = [
    ['Type', VARIANT_LABELS[spec.variant]],
    ['Length', `About ${spec.targetWords.toLocaleString()} words${spec.limits.map((l) => (l.type === 'PAGE' ? `; at most ${l.max} pages` : l.type === 'WORD' ? `; at most ${l.max.toLocaleString()} words` : '')).join('')}`],
    ...(spec.fields.length ? [['Form boxes', spec.fields.map((f) => `${f.label} (${f.maxCharacters ? `${f.maxCharacters} characters` : `${f.maxWords} words`})`).join('; ')] as [string, string]] : []),
    ...(spec.directives.length ? [['The question asks you to', spec.directives.map((d) => d.replace(/_/g, ' ')).join(', ')] as [string, string]] : []),
    ...(spec.coverage.length ? [['Parts to answer', spec.coverage.map((c) => c.text).join(' | ')] as [string, string]] : []),
    ['Referencing', { APA7: 'APA 7th edition', APA6: 'APA 6th edition', HARVARD: 'Harvard' }[spec.citationStyle]],
    ...(work.kind === 'COURSEWORK' ? [['Sources', spec.sourcePolicy === 'CLOSED' ? 'Only your set readings' : 'Independent research'] as [string, string]] : []),
    ...(work.kind === 'COURSEWORK'
      ? [['Rule on AI', { BANNED: 'Not allowed: a note goes on the last page of your Word document', ALLOWED_WITH_DISCLOSURE: 'Allowed with a disclosure statement', ALLOWED: 'Allowed', UNKNOWN: 'Not mentioned' }[spec.aiPolicy]] as [string, string]]
      : []),
    ...(spec.ceiling !== null ? [['Funding ceiling', money(spec.ceiling, spec.currency || '')] as [string, string]] : []),
    ...(spec.durationMonths ? [['Duration', `${spec.durationMonths} months`] as [string, string]] : []),
    ...(spec.priorities.length ? [['Funder priorities', spec.priorities.join('; ')] as [string, string]] : []),
    ...(spec.scoring.length ? [['Scoring', spec.scoring.map((c) => `${c.name}${c.weight ? ` (${c.weight})` : ''}`).join('; ')] as [string, string]] : []),
    ...(spec.templateHeadings.length ? [['Required headings', spec.templateHeadings.join('; ')] as [string, string]] : []),
  ]
  return (
    <div className="space-y-5">
      <Card className="space-y-4 p-5">
        <p className="text-base font-semibold">PaperAid understood</p>
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[12rem_1fr]">
          {summary.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-fg-subtle">{k}</dt>
              <dd className="text-fg">{v}</dd>
            </div>
          ))}
        </dl>
        {spec.overridden.length > 0 && <p className="text-xs text-fg-subtle">Your documents set: {spec.overridden.join('; ')}.</p>}
        {spec.assumptions.length > 0 && (
          <Alert tone="info" title="Assumptions PaperAid made">
            <ul className="list-disc pl-4">
              {spec.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </Alert>
        )}
        {work.kind === 'COURSEWORK' && spec.aiPolicy === 'UNKNOWN' && (
          <Checkbox label="Add PaperAid's note on the last page of the Word document" checked={work.aiNote} onChange={(e) => run(() => data.works.setAiNote(work.id, e.target.checked))} />
        )}
      </Card>
      {external.length > 0 && (
        <Card className="p-5">
          <p className="mb-3 text-base font-semibold">Requirements read from your documents</p>
          <ul className="space-y-3">
            {external.map((r) => (
              <li key={r.id} className="text-sm">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {r.verified ? <CheckCircle2 className="size-4 text-brand-700" aria-label="Found word for word" /> : <CircleAlert className="size-4 text-amber-600" aria-label="Not found word for word" />}
                  {r.label}: {r.value}
                  {r.inConflict && <Badge tone="danger">Your documents disagree</Badge>}
                </p>
                {r.quote && (
                  <p className="mt-1 flex gap-1.5 text-xs text-fg-muted">
                    <Quote className="size-3 shrink-0" aria-hidden /> “{r.quote}” — {r.source}
                    {r.location ? `, ${r.location}` : ''}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card className="space-y-4 p-5">
        <p className="text-base font-semibold">Your details</p>
        <Input label="Title or topic" value={details.title} maxLength={300} onChange={(e) => setDetails({ ...details, title: e.target.value })} />
        <TextArea label={work.kind === 'COURSEWORK' ? 'The assignment question' : 'Your idea'} rows={4} maxLength={8000} value={details.description} onChange={(e) => setDetails({ ...details, description: e.target.value })} />
        {work.variant === 'REFLECTIVE' && (
          <TextArea label="Your experience, in your own words" rows={6} maxLength={8000} value={details.experience} onChange={(e) => setDetails({ ...details, experience: e.target.value })}
            hint="PaperAid never invents your experience: it works only from what you write here." />
        )}
        <Button size="sm" variant="secondary" loading={busy} onClick={() => run(() => data.works.updateDetails(work.id, { ...details, answers: work.inputs.answers }, {}, work.specVersion))}>
          Save details
        </Button>
      </Card>
      {open.length > 0 && (
        <Card className="space-y-4 p-5">
          <p className="text-base font-semibold">Questions</p>
          <p className="text-xs text-fg-subtle">Each answer is saved as soon as you give it.</p>
          {open.filter((q) => q.id !== 'experience').map((q) => (
            <div key={q.id}>
              <QuestionField spec={spec} question={q} value={value(q.id)} onChange={(v) => set(q.id, v)} onCommit={(v) => save(q.id, v)} />
              {saving[q.id] && (
                <p className={`mt-1 text-xs ${saving[q.id] === 'saved' || saving[q.id] === 'saving' ? 'text-fg-subtle' : 'text-amber-700'}`} role="status">
                  {saving[q.id] === 'saving' ? 'Saving…' : saving[q.id] === 'saved' ? 'Saved.' : saving[q.id]}
                </p>
              )}
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" loading={busy} onClick={() => run(() => data.works.answer(work.id, answers, version.current, true)).then(() => setAnswers({}))}>
              Use PaperAid's defaults for the rest
            </Button>
          </div>
        </Card>
      )}
      {spec.blockers.length > 0 && (
        <Alert tone="warning" title="Before PaperAid can plan">
          <ul className="list-disc pl-4">
            {spec.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </Alert>
      )}
      {error && <Alert tone="warning">{error}</Alert>}
      {work.specStatus !== 'CONFIRMED' ? (
        <div className="space-y-2">
          <Button loading={busy} disabled={spec.gate !== 'PASS' || work.needsRead} onClick={() => run(() => data.works.confirm(work.id, version.current))}>
            This is right: confirm
          </Button>
          {(spec.gate !== 'PASS' || work.needsRead) && whyNot.length > 0 && (
            <div className="text-sm text-fg-muted" role="note">
              <p>You can confirm once:</p>
              <ul className="list-disc pl-5">
                {whyNot.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <Alert tone="success">You confirmed what PaperAid understood.</Alert>
      )}
    </div>
  )
}

function QuestionField({
  spec,
  question: q,
  value,
  onChange,
  onCommit,
}: {
  spec: ResolvedSpec
  question: Question
  value: string
  onChange: (v: string) => void
  onCommit: (v: string) => void
}) {
  const hint = [q.help, q.gate === 'ASK_ONCE' && q.fallback ? `If you skip it: ${q.fallback}` : ''].filter(Boolean).join(' ')
  const label = `${q.label}${q.gate === 'BLOCK' ? ' (needed)' : ''}`
  if (value === SKIPPED) return <p className="text-sm text-fg-muted">{q.label}: skipped. {q.fallback}</p>
  if (q.kind === 'CHOICE' || q.kind === 'BOOL')
    return (
      <Select
        label={label}
        value={value}
        hint={hint}
        onChange={(e) => {
          onChange(e.target.value)
          onCommit(e.target.value)
        }}
      >
        <option value="">Choose…</option>
        {(q.kind === 'BOOL' ? ['yes', 'no'] : q.choices).map((c) => (
          <option key={c} value={c}>
            {answerText(spec, q, c).replace(/_/g, ' ').toLowerCase().replace(/^./, (x) => x.toUpperCase())}
          </option>
        ))}
      </Select>
    )
  if (q.kind === 'LONG')
    return <TextArea label={label} hint={hint} rows={3} maxLength={3000} value={value} onChange={(e) => onChange(e.target.value)} onBlur={(e) => onCommit(e.target.value)} />
  if (q.kind === 'NUMBER') {
    const noLimit = q.id === 'word_limit' && value === NO_LIMIT
    return (
      <div className="space-y-2">
        {!noLimit && (
          <Input
            label={label}
            hint={hint || (q.id === 'word_limit' ? 'For example 3,000 or "3,000 words".' : undefined)}
            inputMode="decimal"
            placeholder={q.id === 'word_limit' ? 'e.g. 3,000' : undefined}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onBlur={(e) => onCommit(e.target.value.trim())}
          />
        )}
        {q.id === 'word_limit' && (
          <Checkbox
            label="My brief gives no word limit"
            checked={noLimit}
            onChange={(e) => {
              const next = e.target.checked ? NO_LIMIT : ''
              onChange(next)
              if (next) onCommit(next)
            }}
          />
        )}
      </div>
    )
  }
  return <Input label={label} hint={hint} value={value} onChange={(e) => onChange(e.target.value)} onBlur={(e) => onCommit(e.target.value.trim())} />
}

// --- the plan ---------------------------------------------------------------------------------------------

function PlanPanel({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const [plan, setPlan] = useState<WorkPlan>(work.plan!)
  const [ackPlan, setAckPlan] = useState(false)
  useEffect(() => setPlan(work.plan!), [work.plan])
  const total = plan.sections.reduce((sum, s) => sum + s.words, 0)
  const target = work.spec?.targetWords ?? total
  const editSection = (key: string, patch: Partial<WorkPlan['sections'][number]>) => setPlan((p) => ({ ...p, sections: p.sections.map((s) => (s.key === key ? { ...s, ...patch } : s)) }))
  return (
    <div className="space-y-4">
      {work.candidatePlan && (
        <Alert tone="info" title="PaperAid made a new plan while you edited yours"
          action={<div className="flex gap-2"><Button size="sm" onClick={() => run(() => data.works.takeCandidate(work.id, true))}>Use it</Button><Button size="sm" variant="secondary" onClick={() => run(() => data.works.takeCandidate(work.id, false))}>Keep mine</Button></div>} />
      )}
      <Card className="space-y-4 p-5">
        <Input label="Title" value={plan.title} maxLength={300} onChange={(e) => setPlan({ ...plan, title: e.target.value })} />
        <TextArea label={work.kind === 'COURSEWORK' ? 'Your central argument' : 'The core idea'} rows={3} maxLength={2000} value={plan.position} onChange={(e) => setPlan({ ...plan, position: e.target.value })} />
        <p className="text-sm text-fg-muted">
          {total.toLocaleString()} of about {target.toLocaleString()} words planned.
        </p>
      </Card>
      {plan.sections.map((s) => (
        <Card key={s.key} className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            {s.locked ? <p className="font-semibold">{s.heading}</p> : <Input className="min-w-60 flex-1" label="Heading" value={s.heading} maxLength={200} onChange={(e) => editSection(s.key, { heading: e.target.value })} />}
            {s.locked && <Badge>Required by your instructions</Badge>}
            <Input className="w-32" label="Words" type="number" min={s.minWords} max={s.maxWords || undefined} value={s.words} onChange={(e) => editSection(s.key, { words: Number(e.target.value) || 0 })} />
            {!s.required && !s.locked && (
              <Button size="sm" variant="secondary" onClick={() => setPlan({ ...plan, sections: plan.sections.filter((x) => x.key !== s.key) })}>
                Remove
              </Button>
            )}
          </div>
          <TextArea label="What it covers" rows={2} maxLength={1500} value={s.brief} onChange={(e) => editSection(s.key, { brief: e.target.value })} />
        </Card>
      ))}
      {plan.questionsForStudent.length > 0 && (
        <Alert tone="info" title="Only you can answer these">
          <ul className="list-disc pl-4">
            {plan.questionsForStudent.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </Alert>
      )}
      {work.planStatus !== 'APPROVED' && <ReviewNotice review={work.planReview} what="plan" acknowledged={ackPlan} onAcknowledge={setAckPlan} />}
      {error && <Alert tone="warning">{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" loading={busy} onClick={() => run(() => data.works.savePlan(work.id, plan, work.planVersion))}>
          Save changes
        </Button>
        <Button loading={busy} disabled={work.planStatus === 'APPROVED' || (!!work.planReview && work.planReview.outcome !== 'APPROVED' && !ackPlan)} onClick={() => run(async () => {
          const saved = JSON.stringify(plan) === JSON.stringify(work.plan) ? work : await data.works.savePlan(work.id, plan, work.planVersion)
          // An edit is not what PaperAid reviewed: show the saved version and ask for confirmation first.
          if (saved.planReview && saved.planReview.outcome !== 'APPROVED' && !ackPlan) return saved
          return data.works.approvePlan(work.id, saved.planVersion, ackPlan ? ['PLAN_OBJECTIONS'] : [])
        })}>
          {work.planStatus === 'APPROVED' ? 'Approved' : 'Approve the plan'}
        </Button>
      </div>
    </div>
  )
}

// --- funding: Results Model and budget ---------------------------------------------------------------------

function ResultsPanel({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const [model, setModel] = useState<ResultsModel>(work.results!)
  const [ackResults, setAckResults] = useState(false)
  useEffect(() => setModel(work.results!), [work.results])
  const num = (v: string) => (v.trim() === '' ? null : Number(v))
  const checks = work.checks.filter((c) => c.id.startsWith('FP-0') && Number(c.id.slice(3)) >= 14 && Number(c.id.slice(3)) <= 36)
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-5">
        <TextArea label="Goal" rows={2} value={model.goal.statement} onChange={(e) => setModel({ ...model, goal: { ...model.goal, statement: e.target.value } })} />
        {model.objectives.map((o, i) => (
          <Input key={o.id} label={`Objective ${o.id}`} value={o.statement} onChange={(e) => setModel({ ...model, objectives: model.objectives.map((x, j) => (j === i ? { ...x, statement: e.target.value } : x)) })} />
        ))}
        {model.outcomes.map((o, i) => (
          <Input key={o.id} label={`Outcome ${o.id} (${o.objectiveId})`} value={o.statement} onChange={(e) => setModel({ ...model, outcomes: model.outcomes.map((x, j) => (j === i ? { ...x, statement: e.target.value } : x)) })} />
        ))}
        {model.outputs.map((o, i) => (
          <Input key={o.id} label={`Output ${o.id} (leads to ${o.outcomeId})`} value={o.statement} onChange={(e) => setModel({ ...model, outputs: model.outputs.map((x, j) => (j === i ? { ...x, statement: e.target.value } : x)) })} />
        ))}
      </Card>
      <Card className="space-y-3 p-5">
        <p className="font-semibold">Activities</p>
        {model.activities.map((a, i) => (
          <div key={a.id} className="grid gap-2 sm:grid-cols-[1fr_8rem_5rem_5rem]">
            <Input label={`${a.id} (${a.outputId})`} value={a.statement} onChange={(e) => setModel({ ...model, activities: model.activities.map((x, j) => (j === i ? { ...x, statement: e.target.value } : x)) })} />
            <Input label="Responsible" value={a.ownerRole} onChange={(e) => setModel({ ...model, activities: model.activities.map((x, j) => (j === i ? { ...x, ownerRole: e.target.value } : x)) })} />
            <Input label="From month" type="number" min={1} value={a.startMonth ?? ''} onChange={(e) => setModel({ ...model, activities: model.activities.map((x, j) => (j === i ? { ...x, startMonth: num(e.target.value) } : x)) })} />
            <Input label="To month" type="number" min={1} value={a.endMonth ?? ''} onChange={(e) => setModel({ ...model, activities: model.activities.map((x, j) => (j === i ? { ...x, endMonth: num(e.target.value) } : x)) })} />
          </div>
        ))}
      </Card>
      <Card className="space-y-3 p-5">
        <p className="font-semibold">Indicators</p>
        <p className="text-xs text-fg-muted">Baselines and targets are yours: PaperAid never supplies them.</p>
        {model.indicators.map((ind, i) => (
          <div key={ind.id} className="grid gap-2 sm:grid-cols-[1fr_6rem_6rem_6rem]">
            <Input label={`${ind.id} (${ind.level} ${ind.resultId})`} value={ind.definition} onChange={(e) => setModel({ ...model, indicators: model.indicators.map((x, j) => (j === i ? { ...x, definition: e.target.value } : x)) })} />
            <Input label="Unit" value={ind.unit} onChange={(e) => setModel({ ...model, indicators: model.indicators.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)) })} />
            <Input label="Baseline" type="number" value={ind.baseline ?? ''} onChange={(e) => setModel({ ...model, indicators: model.indicators.map((x, j) => (j === i ? { ...x, baseline: num(e.target.value) } : x)) })} />
            <Input label="Target" type="number" value={ind.target ?? ''} onChange={(e) => setModel({ ...model, indicators: model.indicators.map((x, j) => (j === i ? { ...x, target: num(e.target.value) } : x)) })} />
          </div>
        ))}
      </Card>
      {checks.length > 0 && <ReadinessList items={checks} />}
      {work.resultsStatus !== 'APPROVED' && <ReviewNotice review={work.resultsReview} what="Results Model" acknowledged={ackResults} onAcknowledge={setAckResults} />}
      {error && <Alert tone="warning">{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" loading={busy} onClick={() => run(() => data.works.saveResults(work.id, model, work.resultsVersion))}>
          Save changes
        </Button>
        <Button loading={busy} disabled={work.resultsStatus === 'APPROVED' || (!!work.resultsReview && work.resultsReview.outcome !== 'APPROVED' && !ackResults)} onClick={() => run(async () => {
          const saved = JSON.stringify(model) === JSON.stringify(work.results) ? work : await data.works.saveResults(work.id, model, work.resultsVersion)
          if (saved.resultsReview && saved.resultsReview.outcome !== 'APPROVED' && !ackResults) return saved
          return data.works.approveResults(work.id, saved.resultsVersion, ackResults ? ['RESULTS_OBJECTIONS'] : [])
        })}>
          {work.resultsStatus === 'APPROVED' ? 'Approved' : 'Approve the Results Model'}
        </Button>
      </div>
    </div>
  )
}

function BudgetPanel({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const [budget, setBudget] = useState<Budget>(work.budget!)
  useEffect(() => setBudget(work.budget!), [work.budget])
  const totals = work.budgetTotals
  const edit = (i: number, patch: Partial<BudgetLine>) => setBudget({ ...budget, lines: budget.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) })
  const nextId = () => `B${Math.max(0, ...budget.lines.map((l) => Number(l.id.slice(1)) || 0)) + 1}`
  const checks = work.checks.filter((c) => ['FP-037', 'FP-038', 'FP-039', 'FP-040', 'FP-041', 'FP-042', 'FP-043', 'FP-044', 'FP-045', 'FP-046', 'FP-047', 'FP-054', 'CN-022'].includes(c.id))
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <Input label="Currency" value={budget.currency} maxLength={8} onChange={(e) => setBudget({ ...budget, currency: e.target.value.toUpperCase() })} />
          <Input label="Amount requested" type="number" value={budget.requested ?? ''} onChange={(e) => setBudget({ ...budget, requested: e.target.value ? Number(e.target.value) : null })} hint="Leave empty to request the budget's total." />
          <Input label="Your cost share" type="number" value={budget.costShareProvided ?? ''} onChange={(e) => setBudget({ ...budget, costShareProvided: e.target.value ? Number(e.target.value) : null })} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[48rem] text-sm">
            <thead className="text-left text-xs text-fg-subtle">
              <tr>
                <th className="p-1">Line</th>
                <th className="p-1">Category</th>
                <th className="p-1">Description</th>
                <th className="p-1">Quantity</th>
                <th className="p-1">Unit</th>
                <th className="p-1">Unit cost</th>
                <th className="p-1">Year</th>
                <th className="p-1">Activities</th>
                <th className="p-1 text-right">Total</th>
                <th className="p-1" />
              </tr>
            </thead>
            <tbody>
              {budget.lines.map((l, i) => (
                <tr key={l.id} className="border-t border-line">
                  <td className="p-1 text-fg-subtle">{l.id}</td>
                  <td className="p-1"><input className="w-full rounded border border-line px-1.5 py-1" aria-label="Category" value={l.category} onChange={(e) => edit(i, { category: e.target.value })} /></td>
                  <td className="p-1"><input className="w-full rounded border border-line px-1.5 py-1" aria-label="Description" value={l.description} onChange={(e) => edit(i, { description: e.target.value })} /></td>
                  <td className="p-1"><input className="w-20 rounded border border-line px-1.5 py-1" aria-label="Quantity" type="number" min={0} value={l.quantity} onChange={(e) => edit(i, { quantity: Number(e.target.value) || 0 })} /></td>
                  <td className="p-1"><input className="w-20 rounded border border-line px-1.5 py-1" aria-label="Unit" value={l.unit} onChange={(e) => edit(i, { unit: e.target.value })} /></td>
                  <td className="p-1"><input className="w-24 rounded border border-line px-1.5 py-1" aria-label="Unit cost" type="number" min={0} value={l.unitCost} onChange={(e) => edit(i, { unitCost: Number(e.target.value) || 0 })} /></td>
                  <td className="p-1"><input className="w-14 rounded border border-line px-1.5 py-1" aria-label="Year" type="number" min={1} value={l.year} onChange={(e) => edit(i, { year: Number(e.target.value) || 1 })} /></td>
                  <td className="p-1"><input className="w-24 rounded border border-line px-1.5 py-1" aria-label="Activities" value={l.activityIds.join(', ')} onChange={(e) => edit(i, { activityIds: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} /></td>
                  <td className="p-1 text-right whitespace-nowrap">{totals?.lines[l.id] !== undefined ? money(totals.lines[l.id], totals.currency) : '—'}</td>
                  <td className="p-1">
                    <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label={`Remove line ${l.id}`} onClick={() => setBudget({ ...budget, lines: budget.lines.filter((_, j) => j !== i) })}>
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setBudget({ ...budget, lines: [...budget.lines, { id: nextId(), category: '', description: '', quantity: 0, unit: '', unitCost: 0, enteredTotal: null, year: 1, activityIds: [], support: false, role: '' }] })}>
          <Plus className="size-4" aria-hidden /> Add a line
        </Button>
        {totals && (
          <p className="text-sm font-semibold">
            Total (calculated by PaperAid when you save): {money(totals.total, totals.currency)}
          </p>
        )}
      </Card>
      {checks.length > 0 && <ReadinessList items={checks} />}
      {error && <Alert tone="warning">{error}</Alert>}
      <Button loading={busy} onClick={() => run(() => data.works.saveBudget(work.id, budget, work.budgetVersion))}>
        Save the budget
      </Button>
    </div>
  )
}

// --- the document --------------------------------------------------------------------------------------------

/** A table as the Word file shows it: a section's own table or one PaperAid renders from your data. */
function DataTable({ caption, rows }: { caption: string; rows: string[][] }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <p className="mb-1 text-sm font-semibold">{caption}</p>
      <table className="w-full min-w-[36rem] border border-line text-xs">
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className={r === 0 ? 'bg-surface-subtle font-semibold' : 'border-t border-line'}>
              {row.map((cell, c) => (
                <td key={c} className="p-1.5 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DocumentPanel({ work, onChange, onStarted }: { work: Work; onChange: (w: Work) => void; onStarted: () => void }) {
  const data = useData()
  const { busy, error, run } = useAction(onChange)
  const [doc, setDoc] = useState<WorkDocumentView | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [instruction, setInstruction] = useState('')
  const [chosen, setChosen] = useState<string[]>([])
  useEffect(() => {
    setDoc(null)
    data.works
      .document(work.id, work.current)
      .then(setDoc)
      .catch((e: unknown) => setLoadError(e instanceof DataError ? e.message : 'We could not load the document.'))
  }, [data, work.id, work.current])
  if (loadError) return <Alert tone="danger">{loadError}</Alert>
  if (!doc) return <Skeleton className="h-64 rounded-2xl" />
  const fileName = `${doc.title.slice(0, 70)}.docx`
  const download = (pdf: boolean) =>
    (pdf ? data.works.downloadPdf(work.id, fileName.replace(/\.docx$/, '.pdf'), work.current) : data.works.download(work.id, fileName, work.current)).catch((e: unknown) =>
      setLoadError(e instanceof DataError ? e.message : 'The file could not be prepared.'),
    )
  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <ReadinessBadge status={doc.status} />
        <span className="text-sm text-fg-muted">{doc.words.toLocaleString()} words</span>
        {work.documents.length > 1 && (
          <Select label="Version" value={String(work.current)} onChange={(e) => run(() => data.works.setVersion(work.id, Number(e.target.value)))}>
            {work.documents.map((d) => (
              <option key={d.version} value={d.version}>
                Version {d.version}
                {d.note ? `: ${d.note}` : ''}
              </option>
            ))}
          </Select>
        )}
        <div className="ml-auto flex gap-2">
          <Button size="sm" onClick={() => download(false)}>
            <Download className="size-4" aria-hidden /> Word
          </Button>
          <Button size="sm" variant="secondary" onClick={() => download(true)}>
            PDF
          </Button>
        </div>
      </Card>
      {doc.exploratory && <Alert tone="warning">Exploratory draft: not every eligibility criterion is met, so it is not ready to submit.</Alert>}
      <Card className="space-y-5 p-5">
        {doc.sections.map((s) => (
          <section key={s.key}>
            <h3 className="font-semibold">{s.heading}</h3>
            {s.paragraphs.map((p, i) => (
              <p key={i} className="mt-2 text-sm leading-relaxed text-fg">
                {p}
              </p>
            ))}
            {s.fieldLimit && <p className="mt-1 text-xs text-fg-subtle">{s.fieldCount} (limit {s.fieldLimit})</p>}
            {s.table && <DataTable caption={s.tableCaption || s.heading} rows={s.table} />}
          </section>
        ))}
        {doc.tables.map((t) => (
          <DataTable key={t.caption} caption={t.caption} rows={t.rows} />
        ))}
        {doc.references.length > 0 && (
          <section>
            <h3 className="font-semibold">References</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {doc.references.map((r) => (
                <li key={r} className="pl-6 -indent-6">
                  {r}
                </li>
              ))}
            </ul>
          </section>
        )}
        {doc.aiNote && <p className="border-t border-line pt-3 text-sm text-fg-muted">Last page: {doc.aiNote}</p>}
      </Card>
      <Card className="p-5">
        <p className="mb-3 text-base font-semibold">PaperAid's checks</p>
        <ReadinessList items={doc.readiness} />
        <p className="mt-2 text-xs text-fg-subtle">PaperAid's assessment against your requirements, not a grade, an approval or a funding decision.</p>
      </Card>
      <Card className="space-y-3 p-5">
        <p className="text-base font-semibold">Ask for changes</p>
        <TextArea label="What would you like changed?" rows={3} maxLength={2000} value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        <div className="flex flex-wrap gap-3">
          {doc.sections.map((s) => (
            <Checkbox key={s.key} label={s.heading} checked={chosen.includes(s.key)} onChange={(e) => setChosen(e.target.checked ? [...chosen, s.key] : chosen.filter((k) => k !== s.key))} />
          ))}
        </div>
        <Button size="sm" variant="secondary" loading={busy} disabled={instruction.trim().length < 3} onClick={() => run(() => data.works.requestChanges(work.id, instruction, chosen)).then(() => { setInstruction(''); setChosen([]) })}>
          Add this request
        </Button>
        {work.requests.filter((r) => r.status === 'OPEN').map((r) => (
          <p key={r.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1">{r.text}</span>
            <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label="Remove request" onClick={() => run(() => data.works.removeRequest(work.id, r.id))}>
              <Trash2 className="size-4" aria-hidden />
            </button>
          </p>
        ))}
        {work.requests.some((r) => r.status === 'OPEN') && !work.activeJob && (
          <WorkStepRunner workId={work.id} step="REVISE" label="Make my changes" withNote={false} onStarted={onStarted} description="PaperAid revises the sections you chose and checks them again." />
        )}
        {error && <Alert tone="warning">{error}</Alert>}
      </Card>
    </div>
  )
}
