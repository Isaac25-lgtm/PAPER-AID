import { clsx } from 'clsx'
import { ArrowRight, Check, ChevronDown, Download, ExternalLink, FileText, Info, Lightbulb, Lock, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { DataError, useData } from '../../lib/data'
import { Button } from '../../components/ui/button'
import { Badge, Card } from '../../components/ui/primitives'
import { formatBytes, formatDate, formatNumber } from '../../lib/format'
import { REASON_LABELS } from '../../lib/services'
import type { AnalysisResult, Band, ChangedBlock, CheckedClaim, Finding, FormattingResult, LatexResult, OutputFile, PaperCheck, PaperChecks, ReasonCode, RefinementResult, ResearchResult, Source } from '../../lib/types'

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

function ChangeItem({ change, deep }: { change: ChangedBlock; deep: boolean }) {
  return (
    <details className="group rounded-xl border border-line bg-white shadow-card open:shadow-raised" open={change.kept}>
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-fg-subtle">{change.section}</span>
          <span className="mt-0.5 block truncate text-sm text-fg">{change.kept ? change.before : change.after}</span>
        </span>
        {change.kept ? <Badge tone="warning">Kept original</Badge> : <Badge tone="brand">{deep ? 'Redrafted' : 'Refined'}</Badge>}
        <ChevronDown className="size-4 shrink-0 text-fg-subtle transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="grid gap-3 border-t border-line p-4 lg:grid-cols-2">
        <div className="rounded-lg bg-rose-50/70 p-3">
          <p className="text-xs font-semibold text-rose-800">Your original</p>
          <p className="mt-1.5 font-serif text-[0.95rem] leading-relaxed whitespace-pre-line text-fg-muted">{change.before}</p>
        </div>
        <div className={clsx('rounded-lg p-3', change.kept ? 'bg-surface-muted' : 'bg-brand-50')}>
          <p className={clsx('text-xs font-semibold', change.kept ? 'text-fg-subtle' : 'text-brand-800')}>{change.kept ? 'Proposed (not applied)' : deep ? 'Redrafted' : 'Refined'}</p>
          <p className={clsx('mt-1.5 font-serif text-[0.95rem] leading-relaxed whitespace-pre-line', change.kept ? 'text-fg-subtle line-through decoration-fg-subtle/40' : 'text-fg')}>
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
  const deep = refinement.mode === 'REDRAFT'
  const stats = [
    { label: deep ? 'Passages redrafted' : 'Passages refined', value: refinement.refinedBlocks, tone: 'text-brand-700' },
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
        Citations, quotations, numbers and links were locked during {deep ? 'the redraft' : 'refinement'} and checked afterwards. Every change was
        reviewed by an independent accuracy check.
      </p>
      {refinement.method && <p className="text-xs text-fg-subtle">Method: {refinement.method}</p>}
      {refinement.trimmed && (
        <p className="text-xs text-amber-800">Some long passages are shortened here to keep this page fast. Your change report (Word) has every word.</p>
      )}
      {refinement.changes.length === 0 && (
        <p className="rounded-lg bg-surface-subtle p-4 text-sm text-fg-muted">No passages needed changes, so your wording is exactly as you wrote it.</p>
      )}
      <div className="space-y-3">
        {refinement.changes.map((c) => (
          <ChangeItem key={c.blockId} change={c} deep={deep} />
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

const CERTAINTY: Record<PaperCheck['certainty'], { label: string; tone: 'danger' | 'warning' | 'neutral' }> = {
  CONFIRMED: { label: 'Confirmed', tone: 'danger' },
  POSSIBLE: { label: 'Possible', tone: 'warning' },
  UNDETERMINED: { label: "Couldn't check", tone: 'neutral' },
}

const CHECK_TITLES: Record<PaperCheck['kind'], string> = {
  CITED_NOT_LISTED: 'Cited but not in your reference list',
  LISTED_NOT_CITED: 'In your reference list but not cited',
  UNREADABLE_CITATION: 'Citation not checked',
  UNREADABLE_REFERENCE: 'Reference not checked',
  NO_REFERENCE_LIST: 'No reference list found',
  SPELLING_MIXED: 'Mixed spelling conventions',
}

/** Citation and consistency checks: about the paper's integrity, not AI-likeness. */
export function PaperChecksPanel({ checks }: { checks: PaperChecks }) {
  return (
    <div>
      <h3 className="text-base font-semibold">Citations and consistency</h3>
      <p className="mt-1 text-xs text-fg-muted">
        {checks.citationsFound} citations and {checks.referencesFound} references read. These checks are separate from AI-likeness. PaperAid never changes
        your citations; &ldquo;Couldn&rsquo;t check&rdquo; means we make no claim either way.
      </p>
      {checks.items.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 rounded-lg bg-brand-50 p-3 text-sm text-brand-800">
          <Check className="size-4 shrink-0" aria-hidden /> Every citation we read matches your reference list.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {checks.items.map((c, i) => (
            <li key={`${c.kind}-${i}`} className="rounded-xl border border-line bg-white p-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">{CHECK_TITLES[c.kind]}</span>
                <Badge tone={CERTAINTY[c.certainty].tone}>{CERTAINTY[c.certainty].label}</Badge>
              </div>
              {c.item && <p className="mt-1.5 font-serif text-sm break-words text-fg-muted">{c.item}</p>}
              <p className="mt-1 text-sm text-fg">{c.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const SUPPORT: Record<CheckedClaim['support'], { label: string; tone: 'brand' | 'warning' | 'danger' | 'neutral' }> = {
  SUPPORTED: { label: 'Supported', tone: 'brand' },
  PARTLY_SUPPORTED: { label: 'Partly supported', tone: 'warning' },
  CONTRADICTED: { label: 'Contradicted', tone: 'danger' },
  NOT_FOUND: { label: 'Not found in this search', tone: 'neutral' },
  UNCERTAIN: { label: 'Uncertain', tone: 'warning' },
  UNCONFIRMED: { label: 'Found, not confirmed', tone: 'neutral' },
}

const ACCESS: Record<Source['access'], string> = { FULL_TEXT: 'full text read', ABSTRACT: 'abstract only', SNIPPET: 'search snippet only' }

function SourceItem({ source }: { source: Source }) {
  return (
    <li className="rounded-lg bg-surface-subtle p-3 text-sm">
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 font-medium break-words text-brand-800 hover:underline">
        {source.title || source.url}
        <ExternalLink className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      </a>
      <p className="mt-0.5 text-xs text-fg-subtle">
        {[source.publisher, source.published, ACCESS[source.access]].filter(Boolean).join(' · ')}
        {source.scope && ` · covers ${source.scope}`}
      </p>
      {source.passage && <blockquote className="mt-2 border-l-2 border-line-strong pl-3 font-serif text-fg-muted italic">&ldquo;{source.passage}&rdquo;</blockquote>}
      <p className={clsx('mt-1.5 text-xs', source.verified ? 'text-brand-800' : 'text-amber-800')}>
        {source.verified
          ? `Quotation confirmed by PaperAid${source.access === 'ABSTRACT' ? ' in the article’s abstract' : ' on the page'}.`
          : source.readable
            ? 'PaperAid could not find this quotation on the page, so it is not used as evidence.'
            : 'PaperAid could not open this page to confirm the quotation. Check it yourself.'}
      </p>
    </li>
  )
}

/** Claims checked against live sources. The paper itself is never changed by this. */
export function SourceCheckPanel({ research }: { research: ResearchResult }) {
  return (
    <div className="space-y-4">
      <p className="flex gap-2 rounded-lg bg-surface-subtle p-3 text-xs leading-relaxed text-fg-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        We checked the key factual claims in your paper against current sources on {formatDate(research.retrievedOn)}.
        &ldquo;Not found&rdquo; means this limited search found nothing, not that no evidence exists. Read every source yourself before you cite it.
      </p>
      {research.checked < research.candidates && (
        <p className="text-xs text-amber-800">
          {research.checked} of {research.candidates} claims were checked within this job&rsquo;s price.
        </p>
      )}
      {research.claims.length === 0 && <p className="rounded-lg bg-surface-subtle p-4 text-sm text-fg-muted">We found no public factual claims to check in this paper.</p>}
      <ul className="space-y-3">
        {research.claims.map((c) => (
          <li key={c.id} className="rounded-xl border border-line bg-white p-4 shadow-card">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={SUPPORT[c.support].tone}>{SUPPORT[c.support].label}</Badge>
              <span className="text-xs text-fg-subtle">
                {c.section} · {c.cited ? 'cited in your paper' : 'not cited in your paper'}
              </span>
            </div>
            <blockquote className="mt-2.5 font-serif text-[0.95rem] leading-relaxed text-fg">&ldquo;{c.claim}&rdquo;</blockquote>
            {c.note && <p className="mt-2 text-sm text-fg-muted">{c.note}</p>}
            {c.sources.length > 0 && (
              <ul className="mt-3 space-y-2">
                {c.sources.map((s) => (
                  <SourceItem key={s.url} source={s} />
                ))}
              </ul>
            )}
            {!c.cited && c.sources.length > 0 && (c.support === 'SUPPORTED' || c.support === 'PARTLY_SUPPORTED') && (
              <p className="mt-2 text-xs text-brand-800">Your paper doesn&rsquo;t cite a source for this claim. After reading it, you may want to cite one of these.</p>
            )}
          </li>
        ))}
      </ul>
      {research.method && <p className="text-xs text-fg-subtle">Method: {research.method}</p>}
    </div>
  )
}

export function LatexPanel({ latex }: { latex: LatexResult }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {latex.compiled ? (
          <Badge tone="brand">
            <ShieldCheck className="size-3" aria-hidden /> Compiled to PDF by PaperAid
          </Badge>
        ) : (
          <Badge tone="warning">Not compiled: see the warnings</Badge>
        )}
        <span className="text-xs text-fg-subtle">
          {latex.figures} figure{latex.figures === 1 ? '' : 's'} · {latex.equationsConverted} of {latex.equations} equation{latex.equations === 1 ? '' : 's'} converted
        </span>
      </div>
      {latex.warnings.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-sm text-fg-muted">
          {latex.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-fg-muted">Nothing needs checking by hand.</p>
      )}
      <p className="text-xs text-fg-subtle">
        Download the project from Overview. Open it in Overleaf (New project, then Upload project) or compile main.tex with pdfLaTeX. Citations and your reference list are
        kept exactly as written; they are not converted to BibTeX, because that would mean guessing.
      </p>
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
