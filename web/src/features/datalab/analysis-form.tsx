import { clsx } from 'clsx'
import { Plus, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Input, Select } from '../../components/ui/field'
import type { AnalysisKind, AnalysisMethod, AnalysisSpec, DataFilter, DataVariable, MapLevel, Places } from '../../lib/datalab-types'
import { useData } from '../../lib/data'
import { title as varTitle } from './parts'

const MAX_FILTERS = 5
const LEVELS: { id: MapLevel; label: string }[] = [
  { id: 'DISTRICT', label: 'Districts' },
  { id: 'SUBCOUNTY', label: 'Subcounties' },
  { id: 'SUBREGION', label: 'Sub-regions' },
  { id: 'REGION', label: 'Regions' },
]

/** The analysis asked for: its variables, its method, the records it covers and, for a map, what is drawn. */
export function AnalysisForm({ kind, numbers, categories, usable, busy, onRun, objectives }: {
  kind: AnalysisKind; numbers: DataVariable[]; categories: DataVariable[]; usable: DataVariable[]; busy: boolean; objectives: string[]
  onRun: (spec: AnalysisSpec) => void
}) {
  const data = useData()
  const [objective, setObjective] = useState('')
  const [area, setArea] = useState('') // "" (all of Uganda), "region:Central" or "subregion:Acholi"
  const [first, setFirst] = useState('')
  const [second, setSecond] = useState('')
  const [method, setMethod] = useState<AnalysisMethod>('')
  const [groups, setGroups] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [filters, setFilters] = useState<DataFilter[]>([])
  const [level, setLevel] = useState<MapLevel>('DISTRICT')
  const [subcounty, setSubcounty] = useState('')
  const [dataForm, setDataForm] = useState<'RECORDS' | 'TOTALS'>('RECORDS')
  const [total, setTotal] = useState('')
  const [denominator, setDenominator] = useState('')
  const [places, setPlaces] = useState<Places | null>(null)
  useEffect(() => {
    setFirst('')
    setSecond('')
    setMethod(kind === 'COMPARE_TWO' ? 'MEANS' : kind === 'CORRELATE' ? 'PEARSON' : kind === 'MAP' ? 'COUNT' : '')
    setGroups([])
  }, [kind])
  useEffect(() => {
    if (kind === 'MAP' && !places) data.datalab.places().then(setPlaces).catch(() => setPlaces({ regions: ['Central', 'Eastern', 'Northern', 'Western'], subregions: [] }))
  }, [kind, places, data])
  const placesColumns = usable.filter((v) => v.kind === 'CATEGORICAL' || v.kind === 'TEXT')
  const describable = usable.filter((v) => v.kind === 'NUMERIC' || v.kind === 'CATEGORICAL' || v.kind === 'BINARY')
  const options = (list: DataVariable[], exclude = '') => [
    <option key="" value="">Choose…</option>,
    ...list.filter((v) => v.name !== exclude).map((v) => <option key={v.name} value={v.name}>{varTitle(v)}</option>),
  ]
  const groupVar = useMemo(() => categories.find((v) => v.name === second), [categories, second])
  const needsGroups = kind === 'COMPARE_TWO' && groupVar && groupVar.levels.length > 2
  const totals = kind === 'MAP' && dataForm === 'TOTALS'
  const one = kind === 'DESCRIBE' || (kind === 'MAP' && (totals || method === 'COUNT'))
  const mapReady = kind !== 'MAP' || ((level !== 'SUBCOUNTY' || Boolean(subcounty)) && (!totals || (Boolean(total) && (method !== 'RATE' || Boolean(denominator)))))
  const filtersReady = filters.every((f) => (f.op === 'BETWEEN' ? Boolean(f.low || f.high) : f.values.length > 0))
  const ready = (one ? Boolean(first) : Boolean(first && second) && (!needsGroups || (groups.length === 2 && groups[0] !== groups[1]))) && mapReady && filtersReady
  const [scope, place] = area.split(':')

  const run = () =>
    onRun({
      kind, variables: one ? [first] : [first, second], method, groups: needsGroups ? groups : [], question, objective: objective ? Number(objective) : null, filters,
      ...(kind === 'MAP'
        ? { level, subcounty: level === 'SUBCOUNTY' ? subcounty : '', dataForm, total: totals ? total : '', denominator: totals && method === 'RATE' ? denominator : '',
            region: scope === 'region' ? (place as AnalysisSpec['region']) : '', subregion: scope === 'subregion' ? place : '' }
        : {}),
    })

  return (
    <div className="space-y-4 border-t border-line pt-4">
      {kind === 'DESCRIBE' && <Select label="Variable" value={first} onChange={(e) => setFirst(e.target.value)}>{options(describable)}</Select>}
      {kind === 'COMPARE_TWO' && (
        <>
          <Select label="What to compare (a number)" value={first} onChange={(e) => setFirst(e.target.value)}>{options(numbers)}</Select>
          <Select label="The groups" value={second} onChange={(e) => { setSecond(e.target.value); setGroups([]) }}>{options(categories)}</Select>
          {needsGroups && groupVar && (
            <div className="grid gap-3 sm:grid-cols-2">
              {[0, 1].map((i) => (
                <Select key={i} label={i === 0 ? 'First group' : 'Second group'} value={groups[i] ?? ''} onChange={(e) => { const g = [...groups]; g[i] = e.target.value; setGroups(g) }}>
                  <option value="">Choose…</option>
                  {groupVar.levels.map((l) => <option key={l.value} value={l.value}>{l.value}</option>)}
                </Select>
              ))}
            </div>
          )}
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-fg">What does your question compare?</legend>
            <Choice name="method" checked={method === 'MEANS'} onChange={() => setMethod('MEANS')} title="The averages (means)" body="Is the average higher in one group? Uses Welch's t-test." />
            <Choice name="method" checked={method === 'DISTRIBUTIONS'} onChange={() => setMethod('DISTRIBUTIONS')} title="Typical values and spread" body="Do values tend to be higher in one group? Uses the Wilcoxon rank-sum test; better for skewed data." />
          </fieldset>
        </>
      )}
      {kind === 'CROSSTAB' && (
        <>
          <Select label="First category" value={first} onChange={(e) => setFirst(e.target.value)}>{options(categories)}</Select>
          <Select label="Second category" value={second} onChange={(e) => setSecond(e.target.value)}>{options(categories, first)}</Select>
        </>
      )}
      {kind === 'MAP' && (
        <>
          <Select label="Map by" value={level} onChange={(e) => setLevel(e.target.value as MapLevel)}>
            {LEVELS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </Select>
          <Select label="The column with district names" value={first} onChange={(e) => setFirst(e.target.value)}
            hint={level === 'SUBREGION' || level === 'REGION' ? 'Districts are grouped into sub-regions and regions as UBOS defines them.' : undefined}>
            {options(placesColumns)}
          </Select>
          {level === 'SUBCOUNTY' && (
            <Select label="The column with subcounty names" value={subcounty} onChange={(e) => setSubcounty(e.target.value)}
              hint="Subcounty names repeat across districts, so each is matched within its own district.">
              {options(placesColumns, first)}
            </Select>
          )}
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-fg">What is each row of your data?</legend>
            <Choice name="form" checked={dataForm === 'RECORDS'} onChange={() => { setDataForm('RECORDS'); setMethod('COUNT') }} title="One record (a person, household or event)" body="PaperAid counts the records in each area, or averages a number." />
            <Choice name="form" checked={dataForm === 'TOTALS'} onChange={() => { setDataForm('TOTALS'); setMethod('COUNT') }} title="An area's total (one row per area)" body="For example, the cases reported in each district." />
          </fieldset>
          {totals ? (
            <>
              <Select label="The column holding each area's total" value={total} onChange={(e) => setTotal(e.target.value)}>{options(numbers)}</Select>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium text-fg">What should the map show?</legend>
                <Choice name="measure" checked={method === 'COUNT'} onChange={() => setMethod('COUNT')} title="The total itself" body="Counts, not rates: larger areas may simply have more." />
                <Choice name="measure" checked={method === 'RATE'} onChange={() => setMethod('RATE')} title="A rate per 1,000 people" body="The total divided by each area's population." />
              </fieldset>
              {method === 'RATE' && <Select label="The column holding each area's population" value={denominator} onChange={(e) => setDenominator(e.target.value)}>{options(numbers, total)}</Select>}
            </>
          ) : (
            <>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium text-fg">What should the map show?</legend>
                <Choice name="measure" checked={method === 'COUNT'} onChange={() => setMethod('COUNT')} title="The number of records in each area" body="Counts, not rates: larger areas may simply have more." />
                <Choice name="measure" checked={method === 'MEAN'} onChange={() => setMethod('MEAN')} title="The average of a number in each area" body="For example, the average score of the records in each district." />
              </fieldset>
              {method === 'MEAN' && <Select label="The number" value={second} onChange={(e) => setSecond(e.target.value)}>{options(numbers)}</Select>}
            </>
          )}
          <Select label="Area" value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">All of Uganda</option>
            <optgroup label="Regions">{(places?.regions ?? []).map((r) => <option key={r} value={`region:${r}`}>{`${r} region`}</option>)}</optgroup>
            {places && places.subregions.length > 0 && (
              <optgroup label="Sub-regions">{places.subregions.map((s) => <option key={s.name} value={`subregion:${s.name}`}>{s.name}</option>)}</optgroup>
            )}
          </Select>
        </>
      )}
      {kind === 'CORRELATE' && (
        <>
          <Select label="First number" value={first} onChange={(e) => setFirst(e.target.value)}>{options(numbers)}</Select>
          <Select label="Second number" value={second} onChange={(e) => setSecond(e.target.value)}>{options(numbers, first)}</Select>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-fg">What kind of relationship?</legend>
            <Choice name="corr" checked={method === 'PEARSON'} onChange={() => setMethod('PEARSON')} title="A straight-line relationship" body="Pearson's r." />
            <Choice name="corr" checked={method === 'SPEARMAN'} onChange={() => setMethod('SPEARMAN')} title="Higher goes with higher, not necessarily in a line" body="Spearman's rank correlation; better with outliers or ranks." />
          </fieldset>
        </>
      )}
      <FiltersEditor variables={usable} filters={filters} onChange={setFilters} />
      {objectives.length > 0 && (
        <Select label="Which objective does it answer?" value={objective} onChange={(e) => setObjective(e.target.value)} hint="Chapter Four presents the results objective by objective.">
          <option value="">None of them (other results)</option>
          {objectives.map((o, i) => <option key={o} value={String(i + 1)}>{`Objective ${i + 1}: ${o}`}</option>)}
        </Select>
      )}
      <Input label="Your question, in your words (optional)" value={question} maxLength={300} onChange={(e) => setQuestion(e.target.value)} />
      <Button loading={busy} disabled={!ready} onClick={run}>Run the analysis</Button>
    </div>
  )
}

/** "Only include records where…": conditions on any variable that doesn't identify people or places. */
function FiltersEditor({ variables, filters, onChange }: { variables: DataVariable[]; filters: DataFilter[]; onChange: (f: DataFilter[]) => void }) {
  const choosable = variables.filter((v) => !v.flags.includes('PERSONAL') && !v.flags.includes('LOCATION') && v.kind !== 'IDENTIFIER')
  const set = (i: number, change: Partial<DataFilter>) => onChange(filters.map((f, j) => (j === i ? { ...f, ...change } : f)))
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-fg">Only include records where… <span className="font-normal text-fg-muted">(optional)</span></legend>
      {filters.map((f, i) => {
        const v = choosable.find((x) => x.name === f.variable)
        const ranged = v && (v.stored === 'number' || v.stored === 'date') && v.kind !== 'CATEGORICAL' && v.kind !== 'BINARY'
        return (
          <div key={i} className="space-y-2 rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-end gap-2">
              <Select label="Variable" className="min-w-40 flex-1" value={f.variable}
                onChange={(e) => {
                  const next = choosable.find((x) => x.name === e.target.value)
                  const range = next && (next.stored === 'number' || next.stored === 'date') && next.kind !== 'CATEGORICAL' && next.kind !== 'BINARY'
                  set(i, { variable: e.target.value, op: range ? 'BETWEEN' : 'IN', values: [], low: '', high: '' })
                }}>
                <option value="">Choose…</option>
                {choosable.map((x) => <option key={x.name} value={x.name}>{varTitle(x)}</option>)}
              </Select>
              {v && !ranged && (
                <Select label="Rule" value={f.op} onChange={(e) => set(i, { op: e.target.value as DataFilter['op'] })}>
                  <option value="IN">is one of</option>
                  <option value="NOT_IN">is not one of</option>
                </Select>
              )}
              <button type="button" className="mb-1 rounded p-2 text-fg-subtle hover:text-red-600" aria-label="Remove this condition" onClick={() => onChange(filters.filter((_, j) => j !== i))}>
                <X className="size-4" aria-hidden />
              </button>
            </div>
            {v && ranged && (
              <div className="grid gap-2 sm:grid-cols-2">
                <Input label="From" type={v.stored === 'date' ? 'date' : 'number'} value={f.low} onChange={(e) => set(i, { low: e.target.value })} />
                <Input label="To" type={v.stored === 'date' ? 'date' : 'number'} value={f.high} onChange={(e) => set(i, { high: e.target.value })} />
              </div>
            )}
            {v && !ranged && (
              <div className="flex max-h-40 flex-wrap gap-x-4 gap-y-1 overflow-y-auto">
                {v.levels.map((l) => (
                  <label key={l.value} className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" className="size-4 accent-brand-700" checked={f.values.includes(l.value)}
                      onChange={(e) => set(i, { values: e.target.checked ? [...f.values, l.value] : f.values.filter((x) => x !== l.value) })} />
                    {l.value}
                  </label>
                ))}
                {v.levels.length === 0 && <p className="text-xs text-fg-muted">This variable has too many different values to choose from.</p>}
              </div>
            )}
          </div>
        )
      })}
      {filters.length < MAX_FILTERS && (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...filters, { variable: '', op: 'IN', values: [], low: '', high: '' }])}>
          <Plus className="size-4" aria-hidden /> Add a condition
        </Button>
      )}
      {filters.length > 0 && <p className="text-xs text-fg-subtle">A filter must keep at least a few records and leave out none or at least a few, so that no one can be picked out.</p>}
    </fieldset>
  )
}

export function Choice({ name, checked, onChange, title, body }: { name: string; checked: boolean; onChange: () => void; title: string; body: string }) {
  return (
    <label className={clsx('flex cursor-pointer gap-3 rounded-lg border p-3', checked ? 'border-brand-600 bg-brand-50' : 'border-line')}>
      <input type="radio" name={name} checked={checked} onChange={onChange} className="mt-1 accent-brand-700" />
      <span><span className="block text-sm font-medium text-fg">{title}</span><span className="block text-xs text-fg-muted">{body}</span></span>
    </label>
  )
}
