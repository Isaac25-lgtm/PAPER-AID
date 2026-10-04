import { clsx } from 'clsx'
import { ChevronDown, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Alert, Badge } from '../../components/ui/primitives'
import type { AnalysisResult, DataVariable, ReportDocument, ResultTable, VariableFlag, VariableKind } from '../../lib/datalab-types'
import { useData } from '../../lib/data'

export const KIND_LABEL: Record<VariableKind, string> = {
  NUMERIC: 'Number',
  CATEGORICAL: 'Categories',
  BINARY: 'Two categories',
  DATE: 'Date',
  TEXT: 'Free text',
  IDENTIFIER: 'Identifier',
}

/** Which kinds a variable can be set to, by how it is stored (the server checks the same). */
export const KINDS_FOR: Record<DataVariable['stored'], VariableKind[]> = {
  number: ['NUMERIC', 'CATEGORICAL', 'BINARY', 'IDENTIFIER'],
  text: ['CATEGORICAL', 'BINARY', 'TEXT', 'IDENTIFIER'],
  date: ['DATE', 'IDENTIFIER'],
}

export const FLAG_LABEL: Record<VariableFlag, string> = {
  PERSONAL: 'May identify people',
  RECORD_ID: 'Record code',
  SURVEY_DESIGN: 'Survey design?',
  LOCATION: 'Coordinates',
  FEW_VALUES: 'Few values',
  LEADING_ZEROS: 'Code with leading zeros',
  MIXED: 'Numbers and text mixed',
  LONG_NUMBER: 'Long number kept as text',
  DECIMAL_COMMA: 'Numbers with a decimal comma?',
}

export const title = (v: DataVariable) => v.label || v.name

export function TableView({ table }: { table: ResultTable }) {
  return (
    <figure className="overflow-x-auto">
      <figcaption className="mb-1.5 text-sm font-semibold text-fg">{table.title}</figcaption>
      <table className="w-full min-w-[22rem] border-collapse text-sm">
        <thead>
          <tr className="bg-brand-50 text-left text-brand-900">
            {table.columns.map((c, i) => (
              <th key={`${i}-${c}`} scope="col" className="border border-line px-2.5 py-1.5 font-semibold">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className={row[0]?.text === 'Total' ? 'font-semibold' : undefined}>
              {row.slice(0, table.columns.length).map((cell, j) => (
                <td key={j} className={clsx('border border-line px-2.5 py-1.5', j > 0 && 'tabular-nums', cell.suppressed && 'text-fg-subtle')}>
                  {cell.text}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.notes.map((n) => (
        <p key={n} className="mt-1 text-xs text-fg-subtle">
          {n}
        </p>
      ))}
    </figure>
  )
}

function Chart({ projectId, analysisId }: { projectId: string; analysisId: string }) {
  const data = useData()
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let url: string | null = null
    let live = true
    data.datalab
      .chartUrl(projectId, analysisId)
      .then((u) => {
        url = u
        if (live) setSrc(u)
      })
      .catch(() => setSrc(null))
    return () => {
      live = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [data, projectId, analysisId])
  return src ? <img src={src} alt="Chart of this result" className="mx-auto max-h-80 w-auto rounded-lg border border-line bg-white" /> : null
}

const STATUS: Record<AnalysisResult['status'], { label: string; tone: 'brand' | 'warning' | 'danger' }> = {
  VALID: { label: 'Done', tone: 'brand' },
  VALID_WITH_WARNINGS: { label: 'Done, with a caution', tone: 'warning' },
  NOT_ESTIMABLE: { label: 'Could not be calculated', tone: 'danger' },
}

export function ResultCard({ projectId, result, stale, onRemove, onUseMatches }: { projectId: string; result: AnalysisResult; stale: boolean; onRemove: () => void; onUseMatches?: () => void }) {
  const [open, setOpen] = useState(false)
  const r = result.record
  return (
    <article className="space-y-4 rounded-2xl border border-line bg-white p-5 shadow-card">
      <header className="flex flex-wrap items-start gap-2">
        <h3 className="min-w-0 flex-1 text-base font-semibold text-fg">{result.title}</h3>
        <Badge tone={STATUS[result.status].tone}>{STATUS[result.status].label}</Badge>
        {stale && <Badge tone="warning">Out of date: run it again</Badge>}
        <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label={`Remove ${result.title}`} onClick={onRemove}>
          <Trash2 className="size-4" aria-hidden />
        </button>
      </header>
      {result.sentences.map((s) => (
        <p key={s} className="text-sm leading-relaxed text-fg">
          {s}
        </p>
      ))}
      {result.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      {Object.keys(result.matches ?? {}).length > 0 && onUseMatches && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-sm">
          <p className="font-medium text-fg">Suggested matches for names PaperAid couldn't place:</p>
          <ul className="list-disc pl-5 text-fg-muted">
            {Object.entries(result.matches).map(([name, district]) => (
              <li key={name}>
                "{name}" → {district.charAt(0) + district.slice(1).toLowerCase()}
              </li>
            ))}
          </ul>
          <Button size="sm" variant="secondary" onClick={onUseMatches}>
            Use these matches and map again
          </Button>
        </div>
      )}
      {result.estimates.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {result.estimates.map((e) => (
            <li key={e.name} className="rounded-lg bg-surface-muted px-3 py-1.5 text-sm text-fg">
              <span className="font-medium">{e.name}</span> {e.value.toFixed(2)}
              {e.low !== null && e.high !== null && (
                <span className="text-fg-muted">
                  {' '}
                  (95% CI {e.low.toFixed(2)} to {e.high.toFixed(2)})
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {result.tables.map((t) => (
        <TableView key={t.title} table={t} />
      ))}
      {result.chart && <Chart projectId={projectId} analysisId={result.id} />}
      <div>
        <button className="flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
          <ChevronDown className={clsx('size-4 transition-transform', open && 'rotate-180')} aria-hidden /> How this was calculated
        </button>
        {open && (
          <dl className="mt-3 grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[11rem_1fr]">
            <dt className="text-fg-muted">Question</dt>
            <dd>{r.question}</dd>
            <dt className="text-fg-muted">Method</dt>
            <dd>{r.method}</dd>
            <dt className="text-fg-muted">Why this method</dt>
            <dd>{r.why}</dd>
            <dt className="text-fg-muted">Records used</dt>
            <dd>
              {r.rowsUsed.toLocaleString()} of {r.rowsAvailable.toLocaleString()} {r.leftOut.length > 0 && <span className="text-fg-muted">({r.leftOut.join(' ')})</span>}
            </dd>
            {r.coding.length > 0 && (
              <>
                <dt className="text-fg-muted">Coding</dt>
                <dd>{r.coding.join(' ')}</dd>
              </>
            )}
            <dt className="text-fg-muted">Missing values</dt>
            <dd>{r.missing}</dd>
            {r.assumptions.length > 0 && (
              <>
                <dt className="text-fg-muted">Checks</dt>
                <dd>{r.assumptions.join(' ')}</dd>
              </>
            )}
            <dt className="text-fg-muted">Data version</dt>
            <dd>
              Version {r.datasetVersion}
              {r.cleaning.length > 0 && <span className="text-fg-muted"> (after: {r.cleaning.join(' ')})</span>}
            </dd>
            <dt className="text-fg-muted">Significance level</dt>
            <dd>{r.alpha}</dd>
            <dt className="text-fg-muted">Software</dt>
            <dd>{r.software.join(', ')}</dd>
          </dl>
        )}
      </div>
    </article>
  )
}

/** The report as it reads, from the same document the Word file is built from. */
export function ReportView({ projectId, report }: { projectId: string; report: ReportDocument }) {
  let number = 0
  return (
    <article className="space-y-5 rounded-2xl border border-line bg-white p-6 shadow-card sm:p-8">
      <header>
        <h2 className="text-2xl font-bold text-brand-800">{report.title}</h2>
        <p className="text-sm text-fg-muted">{report.subtitle}</p>
      </header>
      {report.sections.map((s) => {
        if (s.level === 1) number += 1
        const resultId = s.key.startsWith('result_') ? s.key.slice(7) : null
        return (
          <section key={s.key} className="space-y-3">
            {s.level === 1 ? (
              <h3 className="text-lg font-semibold text-fg">
                {number}. {s.heading}
              </h3>
            ) : (
              <h4 className="text-base font-semibold text-fg">{s.heading}</h4>
            )}
            {s.paragraphs.map((p) => (
              <p key={p} className="text-sm leading-relaxed text-fg">
                {p}
              </p>
            ))}
            {s.bullets.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-fg">
                {s.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {s.tables.map((t) => (
              <TableView key={t.title} table={t} />
            ))}
            {resultId && s.chart && <Chart projectId={projectId} analysisId={resultId} />}
            {s.notes.map((n) => (
              <p key={n} className="text-xs text-fg-muted italic">
                Note: {n}
              </p>
            ))}
          </section>
        )
      })}
      {report.appendices.map((s) => (
        <section key={s.key} className="space-y-3 border-t border-line pt-4">
          <h3 className="text-base font-semibold text-fg">{s.heading}</h3>
          {s.paragraphs.map((p) => (
            <p key={p} className="text-sm text-fg">
              {p}
            </p>
          ))}
          {s.bullets.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-sm text-fg">
              {s.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
          {s.tables.map((t) => (
            <TableView key={t.title} table={t} />
          ))}
        </section>
      ))}
    </article>
  )
}

export function Confirm({ question, busy, onYes, onNo, more }: { question: string; busy: boolean; onYes: () => void; onNo: () => void; more: number }) {
  return (
    <div className="space-y-3 rounded-2xl border border-brand-200 bg-brand-50/60 p-5">
      <p className="text-base font-medium text-fg">{question}</p>
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={onYes}>
          Yes, make this change
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onNo}>
          No, keep it as it is
        </Button>
      </div>
      {more > 0 && <p className="text-xs text-fg-muted">{more === 1 ? 'One more change to review after this.' : `${more} more changes to review after this.`}</p>}
    </div>
  )
}
