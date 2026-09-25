import { clsx } from 'clsx'
import { ArrowRight, Check, ChevronDown, Download, FileText, Info, Lightbulb, Lock, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { DataError, useData } from '../../lib/data'
import { Button } from '../../components/ui/button'
import { Badge, Card } from '../../components/ui/primitives'
import { formatBytes, formatDate, formatNumber } from '../../lib/format'
import { REASON_LABELS } from '../../lib/services'
import type { AnalysisResult, Band, ChangedBlock, Finding, FormattingResult, OutputFile, ReasonCode, RefinementResult } from '../../lib/types'

const BANDS: { id: Band; label: string; active: string }[] = [
  { id: 'LOW', label: 'Low', active: 'bg-brand-100 text-brand-800 ring-1 ring-inset ring-brand-300' },
  { id: 'MODERATE', label: 'Moderate', active: 'bg-amber-100 text-amber-900 ring-1 ring-inset ring-amber-300' },
  { id: 'HIGH', label: 'High', active: 'bg-rose-100 text-rose-800 ring-1 ring-inset ring-rose-300' },
]

function BandMeter({ band, caption }: { band: Band; caption?: string }) {
  return (
    <div>
      {caption && <p className="mb-1.5 text-xs font-medium text-fg-subtle">{caption}</p>}
      <div className="grid grid-cols-3 gap-1" role="img" aria-label={`Estimated AI-likeness: ${band.toLowerCase()}`}>
        {BANDS.map((b) => (
          <div
            key={b.id}
            className={clsx(
              'rounded-md py-2 text-center text-xs font-semibold transition-colors',
              b.id === band ? b.active : 'bg-surface-muted text-fg-subtle',
            )}
          >
            {b.label}
          </div>
        ))}
      </div>
    </div>
  )
}

export const DISCLAIMER =
  'This estimates formulaic writing patterns. It is not a detector verdict: AI detectors often disagree with each other and can flag human writing.'

export function ScoreCard({ before, after }: { before: AnalysisResult; after?: AnalysisResult | null }) {
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Estimated AI-likeness</h3>
          <p className="mt-0.5 text-xs text-fg-subtle">
          Algorithm {before.algorithmVersion}
          {before.method ? ` · ${before.method}` : ''}
        </p>
        </div>
        <Badge tone="neutral">Confidence: {before.confidence.toLowerCase()}</Badge>
      </div>
      <div className="mt-5 space-y-4">
        <BandMeter band={before.band} caption={after ? 'Before refinement' : undefined} />
        {after && <BandMeter band={after.band} caption="After refinement" />}
      </div>
      <p className="mt-4 text-xs text-fg-muted">
        Based on {formatNumber(before.analysedWords)} analysed words. References, quotations and tables ({formatNumber(before.excludedWords)} words) were
        excluded.
      </p>
      <p className="mt-3 flex gap-2 rounded-lg bg-surface-subtle p-3 text-xs leading-relaxed text-fg-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {DISCLAIMER}
      </p>
    </Card>
  )
}

const severityBar = { minor: 'bg-sky-400', moderate: 'bg-amber-400', major: 'bg-rose-500' }

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className="relative overflow-hidden rounded-xl border border-line bg-white p-4 pl-5 shadow-card">
      <span aria-hidden className={clsx('absolute inset-y-0 left-0 w-1', severityBar[finding.severity])} />
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{REASON_LABELS[finding.reason]}</span>
        <span className="text-xs text-fg-subtle">
          {finding.section} · {finding.severity}
        </span>
      </div>
      <blockquote className="mt-2.5 border-l-2 border-line-strong pl-3 font-serif text-[0.95rem] leading-relaxed text-fg-muted italic">
        {finding.excerpt}
      </blockquote>
      <p className="mt-3 text-sm text-fg">{finding.explanation}</p>
      <p className="mt-2 flex gap-2 text-sm text-brand-800">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
        {finding.suggestion}
      </p>
    </li>
  )
}

export function FindingsList({ findings }: { findings: Finding[] }) {
  const [filter, setFilter] = useState<ReasonCode | 'ALL'>('ALL')
  const [expanded, setExpanded] = useState(false)
  const counts = findings.reduce<Partial<Record<ReasonCode, number>>>((acc, f) => ({ ...acc, [f.reason]: (acc[f.reason] ?? 0) + 1 }), {})
  const visible = findings.filter((f) => filter === 'ALL' || f.reason === filter)
  const shown = expanded ? visible : visible.slice(0, 4)

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter findings">
        {(['ALL', ...Object.keys(counts)] as (ReasonCode | 'ALL')[]).map((key) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            aria-pressed={filter === key}
            className={clsx(
              'min-h-10 rounded-full px-3.5 text-xs font-medium ring-1 transition-colors ring-inset sm:min-h-8',
              filter === key ? 'bg-brand-700 text-white ring-brand-700' : 'bg-white text-fg-muted ring-line-strong hover:ring-brand-300',
            )}
          >
            {key === 'ALL' ? `All findings (${findings.length})` : `${REASON_LABELS[key]} (${counts[key]})`}
          </button>
        ))}
      </div>
      <ul className="mt-4 space-y-3">
        {shown.map((f) => (
          <FindingCard key={f.id} finding={f} />
        ))}
      </ul>
      {visible.length > 4 && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setExpanded(!expanded)}>
          <ChevronDown className={clsx('size-4 transition-transform', expanded && 'rotate-180')} aria-hidden />
          {expanded ? 'Show fewer' : `Show all ${visible.length} findings`}
        </Button>
      )}
    </div>
  )
}

function ChangeItem({ change }: { change: ChangedBlock }) {
  return (
    <details className="group rounded-xl border border-line bg-white shadow-card open:shadow-raised" open={change.kept}>
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-fg-subtle">{change.section}</span>
          <span className="mt-0.5 block truncate text-sm text-fg">{change.kept ? change.before : change.after}</span>
        </span>
        {change.kept ? <Badge tone="warning">Kept original</Badge> : <Badge tone="brand">Refined</Badge>}
        <ChevronDown className="size-4 shrink-0 text-fg-subtle transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="grid gap-3 border-t border-line p-4 lg:grid-cols-2">
        <div className="rounded-lg bg-rose-50/70 p-3">
          <p className="text-xs font-semibold text-rose-800">Your original</p>
          <p className="mt-1.5 font-serif text-[0.95rem] leading-relaxed text-fg-muted">{change.before}</p>
        </div>
        <div className={clsx('rounded-lg p-3', change.kept ? 'bg-surface-muted' : 'bg-brand-50')}>
          <p className={clsx('text-xs font-semibold', change.kept ? 'text-fg-subtle' : 'text-brand-800')}>{change.kept ? 'Proposed (not applied)' : 'Refined'}</p>
          <p className={clsx('mt-1.5 font-serif text-[0.95rem] leading-relaxed', change.kept ? 'text-fg-subtle line-through decoration-fg-subtle/40' : 'text-fg')}>
            {change.after}
          </p>
        </div>
        {change.reason && (
          <p className="text-xs text-fg-muted lg:col-span-2">
            <span className="font-semibold text-fg">Why: </span>
            {change.reason}
          </p>
        )}
        {change.note && <p className="text-xs text-amber-800 lg:col-span-2">{change.note}</p>}
      </div>
    </details>
  )
}

export function ChangesPanel({ refinement }: { refinement: RefinementResult }) {
  const stats = [
    { label: 'Passages refined', value: refinement.refinedBlocks, tone: 'text-brand-700' },
    { label: 'Kept original', value: refinement.keptOriginal, tone: 'text-amber-700' },
    { label: 'Left untouched', value: refinement.untouchedBlocks, tone: 'text-fg' },
  ]
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-3">
        {stats.map((s) => (
          <Card key={s.label} className="p-4">
            <p className={clsx('text-2xl font-bold', s.tone)}>{s.value}</p>
            <p className="mt-0.5 text-xs text-fg-muted">{s.label}</p>
          </Card>
        ))}
      </div>
      <p className="flex items-start gap-2 text-sm text-fg-muted">
        <Lock className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
        Citations, quotations, numbers and links were locked during refinement and checked afterwards. Every change was reviewed by an independent
        accuracy check.
      </p>
      {refinement.method && <p className="text-xs text-fg-subtle">Method: {refinement.method}</p>}
      {refinement.changes.length === 0 && (
        <p className="rounded-lg bg-surface-subtle p-4 text-sm text-fg-muted">No passages needed changes, so your wording is exactly as you wrote it.</p>
      )}
      <div className="space-y-3">
        {refinement.changes.map((c) => (
          <ChangeItem key={c.blockId} change={c} />
        ))}
      </div>
      {refinement.refinedBlocks > refinement.changes.filter((c) => !c.kept).length && (
        <p className="text-xs text-fg-subtle">Showing a sample of changes. Your change report lists every edit.</p>
      )}
    </div>
  )
}

export function FormattingPanel({ formatting }: { formatting: FormattingResult }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-base font-semibold">{formatting.preset}</h3>
        {formatting.bodyTextUnchanged && (
          <Badge tone="brand">
            <ShieldCheck className="size-3" aria-hidden /> Wording unchanged — verified
          </Badge>
        )}
      </div>
      <Card className="divide-y divide-line">
        {formatting.rules.map((r) => (
          <div key={r.label} className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
            <dt className="text-sm font-medium text-fg-muted">{r.label}</dt>
            <dd className="flex items-start gap-2 text-sm text-fg">
              <Check className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
              {r.value}
            </dd>
          </div>
        ))}
      </Card>
      {formatting.evidence && formatting.evidence.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold">Where each rule came from in your guide</h4>
          <ul className="mt-2 space-y-2">
            {formatting.evidence.map((e) => (
              <li key={e.rule} className="rounded-lg bg-surface-subtle px-3 py-2 text-sm">
                <span className="font-medium text-fg">{e.rule}</span>
                <span className="mt-0.5 block font-serif text-fg-muted">&ldquo;{e.quote}&rdquo;</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {formatting.method && <p className="text-xs text-fg-subtle">Method: {formatting.method}</p>}
    </div>
  )
}

export function DownloadList({ jobId, outputs, expiresAt }: { jobId: string; outputs: OutputFile[]; expiresAt: string }) {
  const data = useData()
  const expired = new Date(expiresAt).getTime() < Date.now()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const download = async (o: OutputFile) => {
    setBusy(o.id)
    setError(null)
    try {
      await data.download(jobId, o.id, o.name)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'The download failed. Try again.')
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="space-y-2.5">
      {outputs.map((o) => (
        <div key={o.id} className="flex items-center gap-3 rounded-xl border border-line bg-white p-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
            <FileText className="size-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{o.label}</p>
            <p className="truncate text-xs text-fg-subtle">
              {o.name} · {formatBytes(o.sizeBytes)}
            </p>
          </div>
          <Button size="sm" variant={expired ? 'secondary' : 'subtle'} disabled={expired} loading={busy === o.id} onClick={() => download(o)} aria-label={`Download ${o.label}`}>
            <Download className="size-4" aria-hidden />
            <span className="hidden sm:inline">{expired ? 'Expired' : 'Download'}</span>
          </Button>
        </div>
      ))}
      {expired ? (
        <p className="text-xs text-fg-subtle">These files were deleted on {formatDate(expiresAt)} under our retention policy. The report summary above remains.</p>
      ) : (
        <p className="text-xs text-fg-subtle">Files are deleted automatically on {formatDate(expiresAt)}.</p>
      )}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-800">
          {error}
        </p>
      )}
    </div>
  )
}

export function BandChange({ before, after }: { before: Band; after: Band }) {
  const label = (b: Band) => b.charAt(0) + b.slice(1).toLowerCase()
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
      {label(before)} <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden /> {label(after)}
    </span>
  )
}
