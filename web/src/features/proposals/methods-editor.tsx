import { Button } from '../../components/ui/button'
import { Input, Select, TextArea } from '../../components/ui/field'
import type { MethodsContract, MethodVariable, ObjectiveMethod } from '../../lib/proposal-types'

const ROLES: MethodVariable['role'][] = ['OUTCOME', 'PREDICTOR', 'ADJUSTMENT', 'MEDIATOR', 'MODERATOR', 'EXPLORATORY']
const SCALES: MethodVariable['scale'][] = ['BINARY', 'NOMINAL', 'ORDINAL', 'CONTINUOUS', 'COUNT', 'TEXT', 'UNKNOWN']
const MODELS: ObjectiveMethod['estimator'][] = ['DESCRIPTIVE', 'BINARY_LOGISTIC', 'MULTINOMIAL_LOGISTIC', 'ORDINAL_LOGISTIC', 'LINEAR', 'POISSON', 'NEGATIVE_BINOMIAL', 'THEMATIC', 'OTHER']
const label = (value: string) => value.toLowerCase().replaceAll('_', ' ')

/** Optional study details after generation. This does not add a plan-confirmation step to Start. */
export function MethodsEditor({ value, onChange }: { value: MethodsContract; onChange: (next: MethodsContract) => void }) {
  const variable = (id: string, patch: Partial<MethodVariable>) => onChange({ ...value, variables: value.variables.map((v) => v.id === id ? { ...v, ...patch } : v) })
  const objective = (number: number, patch: Partial<ObjectiveMethod>) => onChange({ ...value, objectives: value.objectives.map((o) => o.objective === number ? { ...o, ...patch } : o) })
  const add = () => {
    const n = Array.from({ length: 99 }, (_, i) => i + 1).find((i) => !value.variables.some((v) => v.id === `V${i}`))
    if (!n) return
    onChange({ ...value, variables: [...value.variables, { id: `V${n}`, label: 'New measurement', role: 'EXPLORATORY', scale: 'UNKNOWN', definition: '', unit: '', instrument: '', period: '', rationale: '' }] })
  }
  return (
    <details className="rounded-xl border border-line p-4">
      <summary className="cursor-pointer font-semibold">Study measurements and analysis</summary>
      <p className="my-3 text-sm text-fg-muted">Keep each objective tied to the measure it answers. Changes mark affected sections for review. Unknown details need your supervisor’s guidance; PaperAid does not certify clinical definitions or statistical power.</p>
      <div className="space-y-5">
        {value.variables.map((v) => (
          <div key={v.id} className="space-y-3 rounded-lg border border-line p-3">
            <Input label={`Measurement ${v.id}`} value={v.label} maxLength={200} onChange={(e) => variable(v.id, { label: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-2">
              <Select label="Role" value={v.role} onChange={(e) => variable(v.id, { role: e.target.value as MethodVariable['role'] })}>
                {ROLES.map((role) => <option key={role} value={role}>{label(role)}</option>)}
              </Select>
              <Select label="Type of measurement" value={v.scale} onChange={(e) => variable(v.id, { scale: e.target.value as MethodVariable['scale'] })}>
                {SCALES.map((scale) => <option key={scale} value={scale}>{label(scale)}</option>)}
              </Select>
            </div>
            <TextArea label="Definition and decision rule" value={v.definition} maxLength={500} onChange={(e) => variable(v.id, { definition: e.target.value })} />
            <Input label="Unit of observation" value={v.unit} maxLength={150} onChange={(e) => variable(v.id, { unit: e.target.value })} />
            <Input label="Instrument or record" value={v.instrument} maxLength={300} onChange={(e) => variable(v.id, { instrument: e.target.value })} />
            <Input label="Observation period" value={v.period} maxLength={150} onChange={(e) => variable(v.id, { period: e.target.value })} />
            <TextArea label="Why this role and measure fit" value={v.rationale} maxLength={400} onChange={(e) => variable(v.id, { rationale: e.target.value })} />
            <Button size="sm" variant="ghost" onClick={() => onChange({ ...value, variables: value.variables.filter((x) => x.id !== v.id), objectives: value.objectives.map((o) => ({ ...o, outcomeId: o.outcomeId === v.id ? '' : o.outcomeId, predictorIds: o.predictorIds.filter((id) => id !== v.id) })) })}>Remove measurement</Button>
          </div>
        ))}
        <Button size="sm" variant="secondary" disabled={value.variables.length >= 24} onClick={add}>Add measurement</Button>
        {value.objectives.map((o) => (
          <div key={o.objective} className="space-y-3 rounded-lg border border-line p-3">
            <p className="font-medium">Objective {o.objective}</p>
            <Select label="Outcome" value={o.outcomeId} onChange={(e) => objective(o.objective, { outcomeId: e.target.value })}>
              <option value="">Not specified</option>
              {value.variables.map((v) => <option key={v.id} value={v.id}>{v.id}: {v.label}</option>)}
            </Select>
            <Input label="Predictor IDs (comma separated)" value={o.predictorIds.join(', ')} onChange={(e) => objective(o.objective, { predictorIds: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
            <Select label="Analysis" value={o.estimator} onChange={(e) => objective(o.objective, { estimator: e.target.value as ObjectiveMethod['estimator'] })}>
              {MODELS.map((model) => <option key={model} value={model}>{label(model)}</option>)}
            </Select>
            <TextArea label="Analysis rationale" value={o.rationale} maxLength={500} onChange={(e) => objective(o.objective, { rationale: e.target.value })} />
            <TextArea label="Assumptions and diagnostics" value={o.diagnostics} maxLength={500} onChange={(e) => objective(o.objective, { diagnostics: e.target.value })} />
            <TextArea label="Transformation and its justification (if any)" value={o.transformation} maxLength={400} onChange={(e) => objective(o.objective, { transformation: e.target.value })} />
          </div>
        ))}
        <TextArea label="Selection units and sampling design" value={value.selectionUnits} maxLength={500} onChange={(e) => onChange({ ...value, selectionUnits: e.target.value })} />
        <TextArea label="Eligible sampling frame, scope and date" value={value.populationFrame} maxLength={500} onChange={(e) => onChange({ ...value, populationFrame: e.target.value })} />
        <TextArea label="Recruitment and coverage" value={value.recruitment} maxLength={500} onChange={(e) => onChange({ ...value, recruitment: e.target.value })} />
        <TextArea label="Planned protections and unresolved permissions" value={value.ethics} maxLength={600} onChange={(e) => onChange({ ...value, ethics: e.target.value })} />
      </div>
    </details>
  )
}
