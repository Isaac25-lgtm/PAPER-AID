import { clsx } from 'clsx'
import { ArrowRight, Check, CheckCircle2, Info, Lightbulb, Loader2, RotateCcw, ShieldCheck, Sparkles, Undo2, Wand2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Alert, Badge, Card, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatNumber } from '../../lib/format'
import { CATEGORY_LABELS, REASON_LABELS } from '../../lib/services'
import type { Band, ChangedBlock, Finding, FindingCategory, Job, JobDocument, PaperCheck, ReferenceCheck, ReferenceVerification } from '../../lib/types'
import { DISCLAIMER, DownloadList } from './report'

type Category = FindingCategory | 'REFERENCES'
const ORDER: Category[] = ['AI_LIKE', 'ACADEMIC', 'EVIDENCE', 'REFERENCES', 'METHOD', 'FORMATTING']
const BAND_STYLE: Record<Band, string> = {
  LOW: 'bg-brand-100 text-brand-800 ring-brand-300',
  MODERATE: 'bg-amber-100 text-amber-900 ring-amber-300',
  HIGH: 'bg-rose-100 text-rose-800 ring-rose-300',
}
const SEVERITY_TINT = { minor: 'bg-sky-50 ring-sky-200', moderate: 'bg-amber-50 ring-amber-200', major: 'bg-rose-50 ring-rose-200' }
const SEVERITY_BAR = { minor: 'bg-sky-400', moderate: 'bg-amber-400', major: 'bg-rose-500' }
const RANK = { minor: 0, moderate: 1, major: 2 }
const CHECK_TITLES: Record<PaperCheck['kind'], string> = {
  CITED_NOT_LISTED: 'Cited but not in your reference list',
  LISTED_NOT_CITED: 'In your reference list but not cited',
  UNREADABLE_CITATION: 'Citation not checked',
  UNREADABLE_REFERENCE: 'Reference not checked',
  NO_REFERENCE_LIST: 'No reference list found',
  SPELLING_MIXED: 'Mixed spelling conventions',
}

const label = (b: Band) => b.charAt(0) + b.slice(1).toLowerCase()

/** The review workspace: the whole paper on the left, findings on the right. Findings can be
 *  dismissed and restored; chosen ones are fixed as a new, priced refinement. On a refined paper
 *  each change can be kept or undone, and the Word file is rebuilt from those choices. */
export function Workspace({ job: initial }: { job: Job }) {
  const data = useData()
  const navigate = useNavigate()
  const [job, setJob] = useState(initial)
  const [doc, setDoc] = useState<JobDocument | null>(null)
  const [docError, setDocError] = useState<string | null>(null)
  const [category, setCategory] = useState<Category | 'ALL'>('ALL')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [active, setActive] = useState<string | null>(null)
  const [showDismissed, setShowDismissed] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'findings' | 'changes'>(initial.refinement ? 'changes' : 'findings')
  const blockRefs = useRef<Record<string, HTMLElement | null>>({})

  useEffect(() => setJob(initial), [initial])
  useEffect(() => {
    data.workspace
      .document(job.id)
      .then(setDoc)
      .catch((e: unknown) => setDocError(e instanceof DataError ? e.message : 'We could not load your paper.'))
  }, [data, job.id])

  const analysis = job.analysis
  const dismissed = new Set(job.dismissed ?? [])
  const rejected = new Set(job.rejectedChanges ?? [])
  const findings = useMemo(() => [...(analysis?.findings ?? []), ...(analysis?.review ?? [])], [analysis])
  const references = (job.paperChecks?.items ?? []).filter((i) => i.certainty !== 'UNDETERMINED')
  const verified = job.references?.items ?? []
  const referenceIssues = references.length + verified.filter((r) => r.retracted || r.status === 'MISMATCH' || r.status === 'NOT_VERIFIED').length
  const open = findings.filter((f) => !dismissed.has(f.id))
  const count = (c: Category) => (c === 'REFERENCES' ? referenceIssues + (verified.length && !referenceIssues ? 1 : 0) : open.filter((f) => f.category === c).length)
  const visible = (showDismissed ? findings : open).filter((f) => category === 'ALL' || f.category === category)
  const byBlock = useMemo(() => {
    const map: Record<string, Finding[]> = {}
    for (const f of open) (map[f.blockId] ??= []).push(f)
    return map
  }, [open])

  // Refined text shown in place: a change covers one paragraph, or (Deep Redraft) a group of them.
  const changes = doc?.changes ?? job.refinement?.changes ?? []
  // Every paragraph of a group carries the group's change: while the rewrite is kept it replaces them
  // all; when the student keeps their own wording, every original paragraph shows (Codex audit M25).
  const changeFor = useMemo(() => {
    const map: Record<string, { change: ChangedBlock; first: boolean }> = {}
    for (const c of changes) {
      if (c.kept) continue
      const ids = doc?.groups[c.blockId] ?? [c.blockId]
      ids.forEach((id, i) => (map[id] = { change: c, first: i === 0 }))
    }
    return map
  }, [changes, doc])
  const liveChanges = changes.filter((c) => !c.kept)

  const focus = (f: Finding) => {
    setActive(f.id)
    blockRefs.current[f.blockId]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const act = async (key: string, run: () => Promise<Job | void>) => {
    setBusy(key)
    setError(null)
    try {
      const next = await run()
      if (next) setJob(next)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(null)
    }
  }
  const fix = (safeOnly: boolean) =>
    act('fix', async () => {
      const draft = await data.workspace.fix(job.id, [...selected], safeOnly)
      navigate(`/app/new?draft=${draft.id}&service=REFINE`)
    })
  const downloadChoices = () =>
    act('rebuild', async () => {
      const rebuilt = await data.workspace.rebuild(job.id)
      const file = rebuilt.outputs.find((o) => o.id === 'paper-reviewed')
      if (file) await data.download(job.id, file.id, file.name)
      return rebuilt
    })

  const selectable = (f: Finding) => f.category !== 'FORMATTING' && f.category !== 'METHOD' && f.category !== 'EVIDENCE'
  const safeCount = open.filter((f) => f.safe).length
  const isCheck = job.selection.writing === 'AI_CHECK'

  return (
    <div className="space-y-6">
      {job.refinement && <ReadySummary job={job} />}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        {/* The paper */}
        <Card className="order-2 min-w-0 p-5 sm:p-8 lg:order-1 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold">{job.refinement ? 'Your paper, with the changes you are keeping' : 'Your paper'}</p>
            <p className="text-xs text-fg-subtle">Highlighted passages have findings. Click one to see it.</p>
          </div>
          {docError ? (
            <Alert tone="warning">{docError}</Alert>
          ) : !doc ? (
            <div className="space-y-3">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : (
            <article className="space-y-3 font-serif text-[0.97rem] leading-relaxed text-fg">
              {doc.blocks.map((b) => {
                const member = changeFor[b.id]
                const own = !!member && rejected.has(member.change.blockId)
                if (member && !member.first && !own) return null // the rest of a redrafted group, replaced by its rewrite
                const change = member?.first ? member.change : undefined
                const text = change && !own ? change.after : b.text
                const marks = byBlock[b.id] ?? []
                const top = marks.reduce<Finding | null>((best, f) => (!best || RANK[f.severity] > RANK[best.severity] ? f : best), null)
                const isActive = marks.some((f) => f.id === active)
                if (b.kind === 'heading' || b.kind === 'title')
                  return (
                    <h3 key={b.id} ref={(el) => void (blockRefs.current[b.id] = el)} className={clsx('pt-3 font-sans font-semibold', b.kind === 'title' ? 'text-xl' : (b.level ?? 1) <= 1 ? 'text-lg' : 'text-base', top && 'rounded-md px-2 ring-1 ' + SEVERITY_TINT[top.severity])}>
                      {text}
                    </h3>
                  )
                return (
                  <p
                    key={b.id}
                    ref={(el) => void (blockRefs.current[b.id] = el)}
                    onClick={top ? () => focus(top) : undefined}
                    className={clsx(
                      'whitespace-pre-line rounded-md',
                      top && 'cursor-pointer px-2 py-1 ring-1 transition-shadow ' + SEVERITY_TINT[top.severity],
                      isActive && 'ring-2 ring-brand-500',
                      change && !own && 'border-l-4 border-brand-400 pl-3',
                      (b.kind === 'reference' || b.kind === 'caption') && 'text-sm text-fg-muted',
                    )}
                  >
                    {text}
                  </p>
                )
              })}
            </article>
          )}
        </Card>

        {/* The review panel */}
        <aside className="order-1 space-y-4 lg:sticky lg:top-20 lg:order-2 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
          {analysis && (
            <Card className="p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold">Estimated AI-likeness</p>
                <Badge>Confidence: {analysis.confidence.toLowerCase()}</Badge>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className={clsx('rounded-lg px-3 py-1.5 text-sm font-bold ring-1 ring-inset', BAND_STYLE[analysis.band])}>{label(analysis.band)}</span>
                {job.analysisAfter && (
                  <>
                    <ArrowRight className="size-4 text-fg-subtle" aria-hidden />
                    <span className={clsx('rounded-lg px-3 py-1.5 text-sm font-bold ring-1 ring-inset', BAND_STYLE[job.analysisAfter.band])}>{label(job.analysisAfter.band)} after</span>
                  </>
                )}
              </div>
              <p className="mt-3 flex gap-2 text-xs leading-relaxed text-fg-subtle">
                <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {DISCLAIMER}
              </p>
            </Card>
          )}

          {job.refinement && (
            <div className="flex gap-1 rounded-lg bg-surface-muted p-1 text-sm font-medium" role="tablist">
              {(['changes', 'findings'] as const).map((v) => (
                <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)} className={clsx('flex-1 rounded-md py-1.5', view === v ? 'bg-white shadow-sm' : 'text-fg-muted')}>
                  {v === 'changes' ? `Changes (${liveChanges.length})` : `Findings (${open.length})`}
                </button>
              ))}
            </div>
          )}

          {error && <Alert tone="danger">{error}</Alert>}

          {view === 'changes' && job.refinement ? (
            <Card className="p-4">
              <p className="text-sm text-fg-muted">Keep each change, or keep your own wording for that passage. Then download a Word file with your choices.</p>
              <ul className="mt-3 space-y-2">
                {liveChanges.map((c) => {
                  const own = rejected.has(c.blockId)
                  return (
                    <li key={c.blockId} className="rounded-lg border border-line p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-medium text-fg-subtle">{c.section}</span>
                        {own ? <Badge>Your wording</Badge> : <Badge tone="brand">Refined</Badge>}
                      </div>
                      <p className="mt-1.5 line-clamp-3 text-sm">{own ? c.before : c.after}</p>
                      {c.reason && <p className="mt-1 line-clamp-2 text-xs text-fg-subtle">Why: {c.reason}</p>}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="mt-1 -ml-2"
                        loading={busy === c.blockId}
                        onClick={() => act(c.blockId, () => data.workspace.setChange(job.id, c.blockId, own))}
                      >
                        {own ? <Check className="size-4" aria-hidden /> : <Undo2 className="size-4" aria-hidden />} {own ? 'Keep the refined version' : 'Keep my wording'}
                      </Button>
                    </li>
                  )
                })}
              </ul>
              {liveChanges.length > 0 && (
                <Button className="mt-4 w-full" loading={busy === 'rebuild'} onClick={downloadChoices}>
                  Download with my choices
                </Button>
              )}
            </Card>
          ) : (
            <Card className="p-4">
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter findings">
                {(['ALL', ...ORDER] as (Category | 'ALL')[])
                  .filter((c) => c === 'ALL' || count(c) > 0)
                  .map((c) => (
                    <button
                      key={c}
                      onClick={() => setCategory(c)}
                      aria-pressed={category === c}
                      className={clsx('rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset', category === c ? 'bg-brand-700 text-white ring-brand-700' : 'text-fg-muted ring-line-strong hover:ring-brand-300')}
                    >
                      {c === 'ALL' ? `All (${open.length + referenceIssues})` : c === 'REFERENCES' ? `${CATEGORY_LABELS[c]} (${referenceIssues})` : `${CATEGORY_LABELS[c]} (${count(c)})`}
                    </button>
                  ))}
              </div>

              {category === 'REFERENCES' || (category === 'ALL' && references.length > 0 && visible.length === 0) ? null : visible.length === 0 ? (
                <p className="mt-4 flex items-center gap-2 text-sm text-fg-muted">
                  <CheckCircle2 className="size-4 text-brand-600" aria-hidden /> Nothing to show here.
                </p>
              ) : (
                <ul className="mt-3 space-y-2.5">
                  {visible.map((f) => {
                    const gone = dismissed.has(f.id)
                    return (
                      <li key={f.id} className={clsx('relative overflow-hidden rounded-lg border p-3 pl-4', f.id === active ? 'border-brand-400 ring-1 ring-brand-300' : 'border-line', gone && 'opacity-60')}>
                        <span aria-hidden className={clsx('absolute inset-y-0 left-0 w-1', SEVERITY_BAR[f.severity])} />
                        <div className="flex items-start gap-2">
                          {isCheck && selectable(f) && !gone && (
                            <input type="checkbox" aria-label={`Select ${REASON_LABELS[f.reason]}`} className="mt-0.5 size-4 accent-brand-700" checked={selected.has(f.id)} onChange={() => toggle(f.id)} />
                          )}
                          <button className="min-w-0 flex-1 text-left" onClick={() => focus(f)}>
                            <span className="block text-sm font-semibold">{REASON_LABELS[f.reason]}</span>
                            <span className="block text-xs text-fg-subtle">
                              {CATEGORY_LABELS[f.category]} · {f.section} · {f.severity}
                            </span>
                          </button>
                        </div>
                        {f.id === active && (
                          <div className="mt-2 space-y-1.5 text-sm">
                            {f.excerpt && <p className="border-l-2 border-line-strong pl-2 font-serif text-fg-muted italic">{f.excerpt}</p>}
                            <p>{f.explanation}</p>
                            <p className="flex gap-1.5 text-brand-800">
                              <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {f.suggestion}
                            </p>
                            {!f.safe && <p className="text-xs text-amber-800">This needs your judgement, so PaperAid will not change it for you.</p>}
                          </div>
                        )}
                        <Button size="sm" variant="ghost" className="mt-1 -ml-2" loading={busy === f.id} onClick={() => act(f.id, () => data.workspace.setFinding(job.id, f.id, !gone))}>
                          {gone ? <RotateCcw className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />} {gone ? 'Restore' : 'Dismiss'}
                        </Button>
                      </li>
                    )
                  })}
                </ul>
              )}

              {(category === 'ALL' || category === 'REFERENCES') && verified.length > 0 && <ReferenceList verification={job.references!} />}
              {(category === 'ALL' || category === 'REFERENCES') && references.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs font-semibold tracking-wide text-fg-subtle uppercase">Citations and your reference list</p>
                  <ul className="mt-2 space-y-2">
                    {references.map((r, i) => (
                      <li key={i} className="rounded-lg border border-line p-3 text-sm">
                        <p className="font-semibold">{CHECK_TITLES[r.kind]}</p>
                        {r.item && <p className="mt-0.5 truncate text-xs text-fg-muted">{r.item}</p>}
                        <p className="mt-1 text-xs text-fg-muted">{r.detail}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {dismissed.size > 0 && (
                <button className="mt-3 text-xs font-medium text-brand-700 hover:underline" onClick={() => setShowDismissed(!showDismissed)}>
                  {showDismissed ? 'Hide dismissed findings' : `Show ${dismissed.size} dismissed`}
                </button>
              )}

              {isCheck && (
                <div className="mt-4 space-y-2 border-t border-line pt-4">
                  <Button className="w-full" disabled={selected.size === 0} loading={busy === 'fix'} onClick={() => fix(false)}>
                    <Wand2 className="size-4" aria-hidden /> Fix selected ({selected.size})
                  </Button>
                  <Button className="w-full" variant="secondary" disabled={safeCount === 0} loading={busy === 'fix'} onClick={() => fix(true)}>
                    <Sparkles className="size-4" aria-hidden /> Fix all safe issues ({safeCount})
                  </Button>
                  <p className="text-xs text-fg-subtle">
                    PaperAid rewrites only those passages, in your voice. It never changes figures, citations, quotations or your methods. You see the price first.
                  </p>
                  <ButtonLink to="/app/new?service=REDRAFT" variant="ghost" size="sm" className="w-full">
                    Or deep-redraft the whole paper <ArrowRight className="size-4" aria-hidden />
                  </ButtonLink>
                </div>
              )}
            </Card>
          )}

          {job.protected && <ProtectedCard job={job} />}
        </aside>
      </div>

      <div>
        <h3 className="mb-3 text-base font-semibold">Your files</h3>
        {busy === 'rebuild' && (
          <p className="mb-2 flex items-center gap-2 text-sm text-fg-muted">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Preparing your file&hellip;
          </p>
        )}
        <DownloadList jobId={job.id} outputs={job.outputs} expiresAt={job.expiresAt} />
      </div>
    </div>
  )
}

const REFERENCE_STATUS: Record<ReferenceCheck['status'], { label: string; tone: 'brand' | 'warning' | 'neutral' }> = {
  VERIFIED: { label: 'Verified', tone: 'brand' },
  PROBABLE: { label: 'Found', tone: 'brand' },
  MISMATCH: { label: 'Details differ', tone: 'warning' },
  NOT_VERIFIED: { label: 'Could not verify', tone: 'neutral' },
}

/** Each reference matched against registered records. "Found" is not "supports your claim". */
function ReferenceList({ verification }: { verification: ReferenceVerification }) {
  const [all, setAll] = useState(false)
  const rank = (r: ReferenceCheck) => (r.retracted ? 0 : r.status === 'MISMATCH' ? 1 : r.status === 'NOT_VERIFIED' ? 2 : 3)
  const items = [...verification.items].sort((a, b) => rank(a) - rank(b))
  const shown = all ? items : items.slice(0, 6)
  const good = items.filter((r) => (r.status === 'VERIFIED' || r.status === 'PROBABLE') && !r.retracted).length
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold tracking-wide text-fg-subtle uppercase">Your references</p>
      <p className="mt-1 text-xs text-fg-muted">
        {good} of {verification.checked} found in scholarly records{verification.total > verification.checked && ` (first ${verification.checked} of ${verification.total} checked)`}. Found means
        the work exists, not that it supports your claim.
      </p>
      <ul className="mt-2 space-y-2">
        {shown.map((r, i) => (
          <li key={i} className="rounded-lg border border-line p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="line-clamp-2 min-w-0 text-xs text-fg">{r.entry}</p>
              <span className="flex shrink-0 gap-1">
                {r.retracted && <Badge tone="danger">Retracted</Badge>}
                <Badge tone={REFERENCE_STATUS[r.status].tone}>{REFERENCE_STATUS[r.status].label}</Badge>
              </span>
            </div>
            {r.note && <p className="mt-1 text-xs text-fg-muted">{r.note}</p>}
          </li>
        ))}
      </ul>
      {items.length > 6 && (
        <button className="mt-2 text-xs font-medium text-brand-700 hover:underline" onClick={() => setAll(!all)}>
          {all ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </div>
  )
}

function ProtectedCard({ job }: { job: Job }) {
  const p = job.protected!
  const rows = [
    ['numbers', p.numbers],
    ['citations', p.citations],
    ['quotations', p.quotations],
    ['links', p.links],
    ['Word elements (fields, footnotes, equations)', p.wordItems],
  ].filter(([, n]) => Number(n) > 0)
  return (
    <Card className="p-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck className="size-4 text-brand-600" aria-hidden /> Protected in your paper
      </p>
      <ul className="mt-2 grid grid-cols-2 gap-1 text-xs text-fg-muted">
        {rows.map(([name, n]) => (
          <li key={String(name)}>
            <span className="font-semibold text-fg">{formatNumber(Number(n))}</span> {name}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-fg-subtle">{job.refinement ? 'Every change was checked to keep all of them exactly.' : 'Any refinement keeps all of these exactly.'}</p>
    </Card>
  )
}

/** "Your document is ready": the outcome at a glance, with what still needs the student. */
function ReadySummary({ job }: { job: Job }) {
  const r = job.refinement!
  const findings = [...(job.analysis?.findings ?? []), ...(job.analysis?.review ?? [])]
  const needsYou = findings.filter((f) => !f.safe && !(job.dismissed ?? []).includes(f.id)).length
  const items = [
    { label: 'Estimated AI-likeness', value: job.analysis ? (job.analysisAfter ? `${label(job.analysis.band)} → ${label(job.analysisAfter.band)}` : label(job.analysis.band)) : '—' },
    { label: r.mode === 'REDRAFT' ? 'Passages redrafted' : 'Passages refined', value: String(r.refinedBlocks) },
    { label: 'Kept your wording', value: String(r.keptOriginal) },
    { label: 'Need your review', value: String(needsYou) },
  ]
  return (
    <Card className="p-5">
      <p className="flex items-center gap-2 text-base font-semibold">
        <CheckCircle2 className="size-5 text-brand-600" aria-hidden /> Your document is ready
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map((i) => (
          <div key={i.label} className="rounded-lg bg-surface-subtle p-3">
            <dt className="text-xs text-fg-subtle">{i.label}</dt>
            <dd className="mt-0.5 text-sm font-semibold">{i.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-brand-800">
        <span className="flex items-center gap-1">
          <Check className="size-3.5" aria-hidden /> References preserved
        </span>
        <span className="flex items-center gap-1">
          <Check className="size-3.5" aria-hidden /> Numbers preserved
        </span>
        <span className="flex items-center gap-1">
          <Check className="size-3.5" aria-hidden /> Meaning checked on every change
        </span>
      </p>
    </Card>
  )
}
