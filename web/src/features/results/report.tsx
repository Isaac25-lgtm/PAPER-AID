import { clsx } from 'clsx'
import { ArrowRight, Check, Download, ExternalLink, FileText, Info, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { DataError, useData } from '../../lib/data'
import { Button } from '../../components/ui/button'
import { Badge, Card } from '../../components/ui/primitives'
import { formatBytes, formatDate } from '../../lib/format'
import type { Band, CheckedClaim, FormattingResult, LatexResult, OutputFile, ResearchResult, Source } from '../../lib/types'

/** Writing-pattern feedback (owner decision 2026-09-30): it never claims to detect AI. */
export const DISCLAIMER = 'This is feedback on how your writing reads. It does not detect AI and is not a judgement of who wrote your paper.'
/** Shown with the AI-likeness score, only when that score is switched on (a validated detector). */
export const SCORE_DISCLAIMER =
  'This estimates formulaic writing patterns. It is not a detector verdict: AI detectors often disagree with each other and can flag human writing.'

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
