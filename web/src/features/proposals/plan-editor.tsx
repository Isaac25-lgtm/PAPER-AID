import { Minus, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Checkbox, Input, Select, TextArea } from '../../components/ui/field'
import { Alert, Card } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { AlignmentRow, EvidenceItem, Project, ProposalPlan, ResearchGap, SampleMethod, SampleSize, StudyType } from '../../lib/proposal-types'
import { PlanStatusBadge, ReviewNotice, STUDY_TYPES } from './shared'

const METHODS: Record<SampleMethod, string> = {
  YAMANE: "Yamane's formula (needs your population size)",
  KREJCIE_MORGAN: 'Krejcie and Morgan (needs your population size)',
  COCHRAN: "Cochran's formula",
  CENSUS: 'Census: everyone in the population',
  SATURATION: 'Until saturation (qualitative)',
  AUTHOR_STATED: 'A number I state, with my reason',
  NOT_APPLICABLE: 'Not applicable (non-empirical study)',
}

const list = (value: string) => value.split(',').map((v) => v.trim()).filter(Boolean)

function ListEditor({ label, items, onChange, add }: { label: string; items: string[]; onChange: (items: string[]) => void; add?: string }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium">{label}</p>
      <ol className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2.5 w-5 shrink-0 text-right text-sm text-fg-subtle">{i + 1}.</span>
            <textarea
              aria-label={`${label} ${i + 1}`}
              rows={2}
              className="w-full rounded-lg border border-line-strong px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              value={item}
              onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))}
            />
            <button type="button" aria-label={`Remove ${label.toLowerCase()} ${i + 1}`} className="mt-2 rounded p-1 text-fg-subtle hover:bg-surface-muted" onClick={() => onChange(items.filter((_, j) => j !== i))}>
              <Minus className="size-4" aria-hidden />
            </button>
          </li>
        ))}
      </ol>
      {add && (
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => onChange([...items, ''])}>
          <Plus className="size-4" aria-hidden /> {add}
        </Button>
      )}
    </div>
  )
}

/** The research gap, built from the evidence: each part editable, with the sources it rests on. */
function GapEditor({ projectId, gap, onChange }: { projectId: string; gap: ResearchGap; onChange: (gap: ResearchGap) => void }) {
  const data = useData()
  const [library, setLibrary] = useState<EvidenceItem[]>([])
  const ids = gap.evidence.join(' ')
  useEffect(() => {
    if (!ids) return
    data.projects.evidence(projectId).then(setLibrary).catch(() => setLibrary([]))
  }, [data, projectId, ids])
  const sources = library.filter((item) => gap.evidence.includes(item.id))
  return (
    <div className="space-y-3 rounded-xl border border-line p-4">
      <p className="text-sm font-semibold">The research gap</p>
      <TextArea label="What is already known" rows={3} value={gap.known} onChange={(e) => onChange({ ...gap, known: e.target.value })} />
      <TextArea label="What is still missing here" rows={2} value={gap.missing} onChange={(e) => onChange({ ...gap, missing: e.target.value })} />
      <TextArea label="What your study adds" rows={2} value={gap.contribution} onChange={(e) => onChange({ ...gap, contribution: e.target.value })} />
      {gap.evidence.length ? (
        <div className="text-sm text-fg-muted">
          <p>Rests on {gap.evidence.length === 1 ? 'one confirmed source' : `${gap.evidence.length} confirmed sources`}:</p>
          <ul className="mt-1 list-disc pl-5">
            {sources.map((s) => (
              <li key={s.id}>
                {s.statement} <span className="text-fg-subtle">({s.source.title})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Alert tone="warning">No confirmed source supports this gap yet. Add what you know from your own reading, or draft a new plan once more evidence is found.</Alert>
      )}
    </div>
  )
}

export function PlanEditor({ project, onSaved }: { project: Project; onSaved: (p: Project) => void }) {
  const data = useData()
  const [plan, setPlan] = useState<ProposalPlan>(project.plan as ProposalPlan)
  // The version this draft was started from. It changes only together with the content (Codex audit
  // 2026-09-28 #9): saving always names it, so a newer plan is never overwritten unseen.
  const [base, setBase] = useState(project.planVersion)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sample, setSample] = useState<{ size: number | null; steps: string; missing: string } | null>(null)

  useEffect(() => {
    if (!dirty && project.plan) {
      setPlan(project.plan) // a finished step or another tab changed it: take content and version together
      setBase(project.planVersion)
    }
  }, [project.plan, project.planVersion, dirty])
  const conflict = dirty && project.planVersion !== base
  const discard = () => {
    if (project.plan) setPlan(project.plan)
    setBase(project.planVersion)
    setDirty(false)
    setError(null)
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      data.projects.sampleSize(project.id, plan.sampleSize).then(setSample).catch(() => setSample(null))
    }, 300)
    return () => clearTimeout(timer)
  }, [data, project.id, plan.sampleSize])

  const set = (patch: Partial<ProposalPlan>) => {
    setPlan((p) => ({ ...p, ...patch }))
    setDirty(true)
  }
  const setSize = (patch: Partial<SampleSize>) => set({ sampleSize: { ...plan.sampleSize, ...patch } })
  const setObjectives = (objectives: string[]) => {
    const rows: AlignmentRow[] = objectives.map((_, i) => plan.alignment.find((r) => r.objective === i + 1) ?? { objective: i + 1, data: '', collection: '', analysis: '' })
    set({ specificObjectives: objectives, alignment: rows })
  }
  const setRow = (objective: number, patch: Partial<AlignmentRow>) =>
    set({ alignment: plan.alignment.map((r) => (r.objective === objective ? { ...r, ...patch } : r)) })

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const saved = await data.projects.savePlan(project.id, plan, base)
      setBase(saved.planVersion)
      setDirty(false)
      onSaved(saved)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not save your plan.')
    } finally {
      setBusy(false)
    }
  }
  const [ackObjections, setAckObjections] = useState(false)
  const [ackSampling, setAckSampling] = useState(false)
  const acknowledge = [...(ackObjections ? ['OBJECTIONS'] : []), ...(ackSampling ? ['SAMPLING'] : [])]
  const needsAck = (project.planReview && project.planReview.outcome !== 'APPROVED' && !ackObjections) || ((project.plan?.samplingAssumed?.length ?? 0) > 0 && !ackSampling)
  const approve = async () => {
    setBusy(true)
    setError(null)
    try {
      onSaved(await data.projects.approvePlan(project.id, project.planVersion, acknowledge))
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not approve your plan.')
    } finally {
      setBusy(false)
    }
  }

  const needsPopulation = plan.sampleSize.method === 'YAMANE' || plan.sampleSize.method === 'KREJCIE_MORGAN' || plan.sampleSize.method === 'CENSUS' || plan.sampleSize.method === 'COCHRAN'
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold">Plan version {project.planVersion}</p>
          <PlanStatusBadge status={project.planStatus} />
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" loading={busy} disabled={!dirty} onClick={save}>
            Save changes
          </Button>
          <Button loading={busy} disabled={dirty || project.planStatus === 'APPROVED' || project.planProblems.length > 0 || !!needsAck} onClick={approve}>
            Approve plan
          </Button>
        </div>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {conflict && (
        <Alert
          tone="warning"
          title="Your plan changed elsewhere"
          action={
            <Button size="sm" variant="secondary" onClick={discard}>
              Discard my edits and load the latest
            </Button>
          }
        >
          A newer version (version {project.planVersion}) was saved from another tab or by a finished step. Your unsaved edits are still here, but saving them would be
          refused: note what you changed, load the latest, and make your edits again.
        </Alert>
      )}
      {!dirty && project.planProblems.length > 0 && (
        <Alert tone="warning" title="Fix these before approving">
          <ul className="list-disc pl-5">
            {project.planProblems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Alert>
      )}
      {plan.questionsForStudent.length > 0 && (
        <Alert tone="info" title="Only you can answer these">
          <ul className="list-disc pl-5">
            {plan.questionsForStudent.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </Alert>
      )}
      {project.planStatus !== 'APPROVED' && <ReviewNotice review={project.planReview} what="plan" acknowledged={ackObjections} onAcknowledge={setAckObjections} />}
      {project.planStatus !== 'APPROVED' && (project.plan?.samplingAssumed?.length ?? 0) > 0 && (
        <Alert tone="info" title="Sample size settings PaperAid assumed">
          <p>The plan gave none, so PaperAid used the usual {project.plan?.samplingAssumed?.join(', ')}. Change them in the sample size settings, or confirm them.</p>
          <div className="mt-2">
            <Checkbox label="I confirm these sample size settings" checked={ackSampling} onChange={(e) => setAckSampling(e.target.checked)} />
          </div>
        </Alert>
      )}
      {project.planStatus === 'APPROVED' && (
        <p className="text-sm text-fg-muted">Chapters are written from this approved plan. If you change a decision, the sections built on it are marked for review.</p>
      )}

      <Card className="space-y-4 p-5">
        <TextArea label="Title" rows={2} value={plan.title} onChange={(e) => set({ title: e.target.value })} />
        <TextArea label="Problem (the core of your problem statement)" rows={4} value={plan.problem} onChange={(e) => set({ problem: e.target.value })} />
        <GapEditor projectId={project.id} gap={plan.researchGap} onChange={(researchGap) => set({ researchGap })} />
        <TextArea label="Purpose (general objective)" rows={2} value={plan.purpose} onChange={(e) => set({ purpose: e.target.value })} />
        <ListEditor label="Specific objectives" items={plan.specificObjectives} onChange={setObjectives} add="Add objective" />
        <Select label="Research questions, hypotheses or propositions" value={plan.questionsKind} onChange={(e) => set({ questionsKind: e.target.value as ProposalPlan['questionsKind'] })} hint="Hypotheses only when you will test them statistically.">
          <option value="QUESTIONS">Research questions</option>
          <option value="HYPOTHESES">Hypotheses</option>
          <option value="PROPOSITIONS">Propositions</option>
        </Select>
        <ListEditor label="One per objective, in the same order" items={plan.researchQuestions} onChange={(items) => set({ researchQuestions: items })} add="Add" />
      </Card>

      <Card className="space-y-4 p-5">
        <p className="text-base font-semibold">Design</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Type of study" value={plan.studyType} onChange={(e) => set({ studyType: e.target.value as StudyType })}>
            {Object.entries(STUDY_TYPES).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </Select>
          <Input label="Work plan length (months)" type="number" min={1} max={48} value={plan.timelineMonths} onChange={(e) => set({ timelineMonths: Number(e.target.value) || 1 })} />
        </div>
        <TextArea label="Research design and why" rows={2} value={plan.design} onChange={(e) => set({ design: e.target.value })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextArea label="Study area" rows={2} value={plan.studyArea} onChange={(e) => set({ studyArea: e.target.value })} />
          <TextArea label="Study population" rows={2} value={plan.population} onChange={(e) => set({ population: e.target.value })} />
        </div>
        <TextArea label="Sampling technique and procedure" rows={2} value={plan.sampling} onChange={(e) => set({ sampling: e.target.value })} />
        <TextArea label="Inclusion and exclusion criteria" rows={2} value={plan.inclusion} onChange={(e) => set({ inclusion: e.target.value })} />
        {plan.studyType !== 'QUALITATIVE' && plan.studyType !== 'NON_EMPIRICAL' && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Independent variables" value={plan.variables.independent.join(', ')} onChange={(e) => set({ variables: { ...plan.variables, independent: list(e.target.value) } })} hint="Separate with commas" />
            <Input label="Dependent variables" value={plan.variables.dependent.join(', ')} onChange={(e) => set({ variables: { ...plan.variables, dependent: list(e.target.value) } })} />
            <Input label="Intervening variables" value={plan.variables.intervening.join(', ')} onChange={(e) => set({ variables: { ...plan.variables, intervening: list(e.target.value) } })} />
          </div>
        )}
        <TextArea label="Theory or framework, and why it fits" rows={2} value={plan.theory} onChange={(e) => set({ theory: e.target.value })} />
        <TextArea label="Scope (geographical, time and content)" rows={2} value={plan.scope} onChange={(e) => set({ scope: e.target.value })} />
      </Card>

      <Card className="space-y-3 p-5">
        <div>
          <p className="text-base font-semibold">How each objective will be answered</p>
          <p className="mt-0.5 text-sm text-fg-muted">The alignment table: Chapter Three is written from it, and an analysis must be able to answer its objective.</p>
        </div>
        {plan.specificObjectives.map((objective, i) => {
          const row = plan.alignment.find((r) => r.objective === i + 1) ?? { objective: i + 1, data: '', collection: '', analysis: '' }
          return (
            <div key={i} className="rounded-xl bg-surface-subtle p-3">
              <p className="text-sm font-medium">
                {i + 1}. {objective || 'Objective'}
              </p>
              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                <Input label="Data needed" value={row.data} onChange={(e) => setRow(i + 1, { data: e.target.value })} />
                <Input label="Collected by" value={row.collection} onChange={(e) => setRow(i + 1, { collection: e.target.value })} />
                <Input label="Analysed by" value={row.analysis} onChange={(e) => setRow(i + 1, { analysis: e.target.value })} />
              </div>
            </div>
          )
        })}
      </Card>

      <Card className="space-y-4 p-5">
        <div>
          <p className="text-base font-semibold">Sample size</p>
          <p className="mt-0.5 text-sm text-fg-muted">PaperAid calculates it from your own figures. It never supplies a population size: give yours and where it comes from.</p>
        </div>
        <Select label="How the sample size is reached" value={plan.sampleSize.method} onChange={(e) => setSize({ method: e.target.value as SampleMethod })}>
          {Object.entries(METHODS).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </Select>
        {needsPopulation && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Accessible population (N)"
              type="number"
              min={1}
              value={plan.sampleSize.population ?? ''}
              onChange={(e) => setSize({ population: e.target.value ? Number(e.target.value) : null })}
              hint={plan.sampleSize.method === 'COCHRAN' ? 'Optional for Cochran: used to adjust for a small population.' : undefined}
            />
            <Input label="Where this figure comes from" value={plan.sampleSize.populationSource} onChange={(e) => setSize({ populationSource: e.target.value })} placeholder="e.g. district health office records, 2025" />
          </div>
        )}
        {(plan.sampleSize.method === 'YAMANE' || plan.sampleSize.method === 'KREJCIE_MORGAN' || plan.sampleSize.method === 'COCHRAN') && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Margin of error" type="number" step={0.01} min={0.01} max={0.2} value={plan.sampleSize.margin} onChange={(e) => setSize({ margin: Number(e.target.value) })} />
            <Select label="Confidence" value={plan.sampleSize.confidence} onChange={(e) => setSize({ confidence: Number(e.target.value) as 90 | 95 | 99 })}>
              <option value={90}>90%</option>
              <option value={95}>95%</option>
              <option value={99}>99%</option>
            </Select>
            <Input label="Expected proportion (p)" type="number" step={0.05} min={0.05} max={0.95} value={plan.sampleSize.proportion} onChange={(e) => setSize({ proportion: Number(e.target.value) })} />
          </div>
        )}
        {(plan.sampleSize.method === 'SATURATION' || plan.sampleSize.method === 'AUTHOR_STATED') && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Number of participants" type="number" min={1} value={plan.sampleSize.stated ?? ''} onChange={(e) => setSize({ stated: e.target.value ? Number(e.target.value) : null })} />
            <Input label="Why that is enough" value={plan.sampleSize.rationale} onChange={(e) => setSize({ rationale: e.target.value })} />
          </div>
        )}
        {sample && (sample.steps || sample.missing) && (
          <p className={sample.missing ? 'rounded-lg bg-amber-50 p-3 text-sm text-amber-900' : 'rounded-lg bg-brand-50 p-3 text-sm text-brand-900'}>{sample.missing || sample.steps}</p>
        )}
      </Card>
      {dirty && (
        <div className="sticky bottom-4 flex justify-end">
          <Button loading={busy} onClick={save}>
            Save changes
          </Button>
        </div>
      )}
    </div>
  )
}
