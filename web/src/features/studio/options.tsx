import { clsx } from 'clsx'
import { ArrowRight, Check, Info, Loader2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Checkbox, Select } from '../../components/ui/field'
import { FileChip, FileDropzone, fileMetaLine } from '../../components/ui/file-dropzone'
import { Alert, Badge, Card, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatTokens } from '../../lib/format'
import { AVAILABILITY_BADGE, INVITE_ONLY_REASON, NOT_CONFIGURED_REASON, SERVICES, STYLE_OPTIONS } from '../../lib/services'
import type { CustomLayout, EstimateView, FileMeta, ImageMeta, Job, Quote, ServiceId, ServiceSelection } from '../../lib/types'
import { useWallet, walletChanged } from '../../lib/use-wallet'
import { DISCLAIMER } from '../results/report'

/** What the panel beside the paper offers: the first check, a full redraft, formatting, or a
 *  prepared draft (passages chosen to fix, or the student's own request for changes). */
export type Mode = 'check' | 'redraft' | 'format' | 'prepared' | 'sources'

const BASE: ServiceSelection = { writing: 'NONE', intensity: 'STANDARD', style: 'PRESERVE_VOICE', sourceCheck: false, formatting: 'NONE', preset: 'apa7', latex: false, proposal: 'NONE', level: 'MASTERS' }
const ACCEPT = '.docx,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf'
const FONTS = ['Times New Roman', 'Calibri', 'Arial', 'Trebuchet MS', 'Georgia', 'Cambria', 'Garamond', 'Book Antiqua']

/** The selection a mode starts from; `service` (from the job chooser) fine-tunes it. */
export function startingSelection(mode: Mode, job: Job, service: string | null): ServiceSelection {
  const style = job.selection.style ?? 'PRESERVE_VOICE'
  if (mode === 'prepared') return { ...BASE, ...job.selection, writing: 'REFINE', style }
  if (job.quote) return { ...BASE, ...job.selection } // coming back to a priced draft: the same choices
  if (mode === 'check') return { ...BASE, writing: 'AI_CHECK', academic: true, sourceCheck: service === 'SOURCE_CHECK' }
  if (mode === 'sources') return { ...BASE, sourceCheck: true } // the results action: the claims only, no new check
  if (mode === 'format')
    return { ...BASE, formatting: service === 'TEMPLATE_FORMAT' ? 'TEMPLATE_FORMAT' : service === 'LATEX' ? 'NONE' : 'FORMAT', latex: service === 'LATEX' }
  return { ...BASE, writing: service === 'REDRAFT' ? 'REDRAFT' : 'REFINE', style, academic: true }
}

const TITLES: Record<Mode, { title: string; body: string; start: string }> = {
  check: {
    title: 'Check my writing',
    body: 'PaperAid reads your paper and marks generic, formulaic or repetitive passages, with the reasons and suggestions. Your paper is not changed.',
    start: 'Check my writing',
  },
  redraft: { title: 'Redraft', body: 'Choose how PaperAid should redraft your paper. You see every change and can keep your own wording for any of them.', start: 'Start redraft' },
  format: { title: 'Format', body: 'Lay your paper out in an academic style. Your wording is not changed.', start: 'Format my paper' },
  prepared: { title: 'Your changes', body: 'PaperAid rewrites only the passages below, following your request, and checks every change.', start: 'Make these changes' },
  sources: { title: 'Check my sources', body: 'PaperAid finds the key factual claims in your paper and checks them against live public sources. Your paper is not changed.', start: 'Check my sources' },
}

interface Pricing {
  quote: Quote | null
  feeCap: number | null
  estimate: EstimateView | null
  loading: boolean
  error: string | null
  needsCredits: boolean
}
const NO_PRICE: Pricing = { quote: null, feeCap: null, estimate: null, loading: false, error: null, needsCredits: false }

function OptionCard({ checked, onSelect, title, body, badge, disabledReason, name }: { checked: boolean; onSelect: () => void; title: string; body: string; badge?: ReactNode; disabledReason?: string; name: string }) {
  return (
    <label
      className={clsx(
        'relative flex cursor-pointer gap-3 rounded-xl border p-3 transition-colors',
        checked ? 'border-brand-500 bg-brand-50/60 ring-1 ring-brand-500' : 'border-line hover:border-brand-300',
        disabledReason && 'cursor-not-allowed bg-surface-subtle hover:border-line',
      )}
    >
      <input type="radio" name={name} checked={checked} disabled={!!disabledReason} onChange={onSelect} className="sr-only" />
      <span aria-hidden className={clsx('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2', checked ? 'border-brand-600 bg-brand-600' : 'border-line-strong bg-white')}>
        {checked && <Check className="size-3 text-white" strokeWidth={3} />}
      </span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-fg">
          {title} {badge}
        </span>
        <span className="mt-0.5 block text-xs leading-relaxed text-fg-muted">{disabledReason ?? body}</span>
      </span>
    </label>
  )
}

function CustomLayoutFields({ value, onChange }: { value: CustomLayout | null; onChange: (v: CustomLayout | null) => void }) {
  const [open, setOpen] = useState(!!value)
  const set = (patch: Partial<CustomLayout>) => {
    const next = { ...(value ?? {}), ...patch }
    onChange(Object.values(next).some((v) => v !== null && v !== undefined) ? next : null)
  }
  const num = (v: string) => (v ? Number(v) : null)
  if (!open)
    return (
      <button type="button" className="mt-2 text-sm font-medium text-brand-700 hover:underline" onClick={() => setOpen(true)}>
        Customise font, size, spacing or margins
      </button>
    )
  return (
    <div className="mt-3 grid gap-3 rounded-xl bg-surface-subtle p-3 sm:grid-cols-2">
      <Select label="Font" value={value?.font ?? ''} onChange={(e) => set({ font: e.target.value || null })}>
        <option value="">Style default</option>
        {FONTS.map((f) => (
          <option key={f}>{f}</option>
        ))}
      </Select>
      <Select label="Font size" value={value?.sizePt ?? ''} onChange={(e) => set({ sizePt: num(e.target.value) })}>
        <option value="">Style default</option>
        {[10, 11, 12, 13, 14].map((s) => (
          <option key={s} value={s}>
            {s} pt
          </option>
        ))}
      </Select>
      <Select label="Line spacing" value={value?.lineSpacing ?? ''} onChange={(e) => set({ lineSpacing: num(e.target.value) })}>
        <option value="">Style default</option>
        {[1, 1.15, 1.5, 2].map((s) => (
          <option key={s} value={s}>
            {s === 1 ? 'Single' : s === 2 ? 'Double' : s}
          </option>
        ))}
      </Select>
      <Select label="Margins" value={value?.marginCm ?? ''} onChange={(e) => set({ marginCm: num(e.target.value) })}>
        <option value="">Style default</option>
        {[2, 2.54, 3, 3.5].map((m) => (
          <option key={m} value={m}>
            {m === 2.54 ? '2.54 cm (1 inch)' : `${m} cm`}
          </option>
        ))}
      </Select>
      <Select label="Alignment" value={value?.alignment ?? ''} onChange={(e) => set({ alignment: (e.target.value || null) as CustomLayout['alignment'] })}>
        <option value="">Style default</option>
        <option value="left">Left</option>
        <option value="justify">Justified</option>
      </Select>
    </div>
  )
}

/** The panel beside the paper for a job not yet started: the choices for this step, its price, and Start. */
export function JobOptions({ job, mode, initial }: { job: Job; mode: Mode; initial: ServiceSelection }) {
  const data = useData()
  const { config } = data
  const { wallet } = useWallet()
  const [selection, setSelection] = useState<ServiceSelection>(initial)
  const [pricing, setPricing] = useState<Pricing>(NO_PRICE)
  const [ownWork, setOwnWork] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [guide, setGuide] = useState<{ name: string; meta: FileMeta | null; error: string | null } | null>(job.guideline ? { name: job.guideline.name, meta: job.guideline, error: null } : null)
  const [logo, setLogo] = useState<{ name: string; meta: ImageMeta | null; error: string | null } | null>(job.logo ? { name: job.logo.name, meta: job.logo, error: null } : null)
  const set = (patch: Partial<ServiceSelection>) => setSelection((s) => ({ ...s, ...patch }))
  const isPdf = job.source?.format === 'PDF'
  const reasonFor = (id: ServiceId, otherwise?: string) =>
    config.availability[id] === 'invite_only' ? INVITE_ONLY_REASON : config.availability[id] === 'not_configured' ? NOT_CONFIGURED_REASON : config.availability[id] === 'soon' ? SERVICES[id].short : otherwise
  const badgeFor = (id: ServiceId) => {
    const availability = config.availability[id]
    return availability === 'available' ? undefined : <Badge>{AVAILABILITY_BADGE[availability]}</Badge>
  }
  const pdfReason = isPdf ? 'Needs the Word file: PDFs can be checked only.' : undefined
  const needsFile = (selection.formatting === 'TEMPLATE_FORMAT' && !guide?.meta) || (!!selection.logo && selection.logo !== 'NONE' && !logo?.meta)

  useEffect(() => {
    if (needsFile) return setPricing(NO_PRICE)
    let cancelled = false
    setPricing({ ...NO_PRICE, loading: true })
    const timer = setTimeout(() => {
      data
        .requestQuote(job.id, selection)
        .then((r) => !cancelled && setPricing({ ...NO_PRICE, quote: r.quote, feeCap: r.estimateFeeCap, estimate: r.estimate }))
        .catch((e: unknown) => !cancelled && setPricing({ ...NO_PRICE, error: e instanceof DataError ? e.message : 'We could not price this.', needsCredits: e instanceof DataError && e.status === 402 }))
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // guide/logo: a new file clears the server's quote
  }, [data, job.id, selection, needsFile, guide?.meta, logo?.meta])

  const estimateRunning = pricing.estimate?.status === 'RUNNING'
  useEffect(() => {
    if (!estimateRunning) return
    const stop = data.watchJob(job.id, (next) => {
      if (!next || next.estimate?.status === 'RUNNING') return
      stop()
      setPricing((p) => ({ ...p, estimate: next.estimate, quote: next.estimate?.status === 'READY' ? next.quote : null }))
      walletChanged()
    })
    return stop
  }, [data, job.id, estimateRunning])

  const runEstimate = async () => {
    setPricing((p) => ({ ...p, loading: true, error: null }))
    try {
      const r = await data.requestQuote(job.id, selection, true)
      setPricing({ ...NO_PRICE, quote: r.quote, feeCap: r.estimateFeeCap, estimate: r.estimate })
    } catch (e) {
      setPricing((p) => ({ ...p, loading: false, error: e instanceof DataError ? e.message : 'We could not start the estimate.' }))
    }
  }

  const uploadGuide = async (file: File) => {
    setGuide({ name: file.name, meta: null, error: null })
    try {
      setGuide({ name: file.name, meta: await data.uploadFile(job.id, 'guideline', file, () => undefined), error: null })
    } catch (e) {
      setGuide({ name: file.name, meta: null, error: e instanceof DataError ? e.message : 'The guide could not be uploaded.' })
    }
  }
  const uploadLogo = async (file: File) => {
    setLogo({ name: file.name, meta: null, error: null })
    try {
      setLogo({ name: file.name, meta: await data.uploadLogo(job.id, file), error: null })
    } catch (e) {
      setLogo({ name: file.name, meta: null, error: e instanceof DataError ? e.message : 'The logo could not be uploaded.' })
    }
  }

  const start = async () => {
    if (!pricing.quote) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await data.submitJob(job.id, pricing.quote.id)
      walletChanged() // the page follows the job from here: the paper stays, progress replaces this panel
    } catch (e) {
      setSubmitError(e instanceof DataError ? e.message : 'We could not start this. Try again.')
      setSubmitting(false)
    }
  }

  const charging = config.creditsEnabled
  const hold = pricing.quote ? pricing.quote.amount - pricing.quote.paid : 0
  const shortOfCredit = charging && !!wallet && !!pricing.quote && wallet.available < hold
  const canStart = !!pricing.quote && ownWork && !pricing.loading && !shortOfCredit && !needsFile
  const text = TITLES[mode]
  const fixing = selection.onlyBlocks?.length ?? 0
  const asked = Object.values(job.fixNotes ?? {}).flat().find((n) => n.startsWith('The student asks:'))

  return (
    <Card className="space-y-4 p-4">
      <div>
        <p className="text-base font-semibold">{text.title}</p>
        <p className="mt-1 text-sm text-fg-muted">{text.body}</p>
      </div>

      {mode === 'prepared' && (
        <Alert tone="info" title={`${fixing} passage${fixing === 1 ? '' : 's'}`}>
          {asked ? <>Your request: &ldquo;{asked.replace('The student asks: ', '')}&rdquo;</> : 'Rewritten following their findings, in your voice. Everything else stays exactly as it is.'}
        </Alert>
      )}

      {(mode === 'check' || mode === 'redraft') && (
        <div>
          <p className="text-sm font-semibold">Is this academic or research work?</p>
          <div className="mt-2 grid gap-2">
            <OptionCard name="academic" checked={selection.academic !== false} onSelect={() => set({ academic: true })} title="Yes" body="Also review academic writing, evidence, methods and references." />
            <OptionCard name="academic" checked={selection.academic === false} onSelect={() => set({ academic: false })} title="No" body="Writing patterns, clarity and structure only." />
          </div>
        </div>
      )}

      {mode === 'redraft' && (
        <>
          <div>
            <p className="text-sm font-semibold">How much should change?</p>
            <div className="mt-2 grid gap-2">
              <OptionCard name="depth" checked={selection.writing === 'REFINE' && selection.intensity === 'LIGHT'} onSelect={() => set({ writing: 'REFINE', intensity: 'LIGHT' })} title="Light" body="Only the clearest issues, up to about a quarter of the paper." disabledReason={reasonFor('REFINE', pdfReason)} />
              <OptionCard name="depth" checked={selection.writing === 'REFINE' && selection.intensity !== 'LIGHT'} onSelect={() => set({ writing: 'REFINE', intensity: 'STANDARD' })} title="Standard" body="Every flagged passage, up to about half of the paper." badge={<Badge tone="brand">Popular</Badge>} disabledReason={reasonFor('REFINE', pdfReason)} />
              <OptionCard name="depth" checked={selection.writing === 'REDRAFT'} onSelect={() => set({ writing: 'REDRAFT' })} title="Deep redraft" body={SERVICES.REDRAFT.short} badge={badgeFor('REDRAFT')} disabledReason={reasonFor('REDRAFT', pdfReason)} />
            </div>
          </div>
        </>
      )}

      {(mode === 'redraft' || mode === 'prepared') && (
        <div>
          <Select label="Writing style" value={selection.style} onChange={(e) => set({ style: e.target.value as ServiceSelection['style'] })}>
            {STYLE_OPTIONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-fg-subtle">{STYLE_OPTIONS.find((s) => s.id === selection.style)?.body}</p>
        </div>
      )}

      {(mode === 'check' || mode === 'redraft') && (
        <Checkbox
          checked={selection.sourceCheck}
          onChange={(e) => set({ sourceCheck: e.target.checked })}
          disabled={!!reasonFor('SOURCE_CHECK')}
          label={
            <>
              <span className="font-semibold text-fg">Check my claims against live sources</span> {badgeFor('SOURCE_CHECK')}
              <span className="mt-0.5 block text-xs">{reasonFor('SOURCE_CHECK') ?? 'The key factual claims, each checked against current sources.'}</span>
            </>
          }
        />
      )}

      {(mode === 'redraft' || mode === 'format' || mode === 'prepared') && (
        <div>
          <p className="text-sm font-semibold">{mode === 'format' ? 'Layout' : 'Formatting (optional)'}</p>
          <div className="mt-2 grid gap-2">
            {mode !== 'format' && <OptionCard name="formatting" checked={selection.formatting === 'NONE'} onSelect={() => set({ formatting: 'NONE' })} title="Keep my layout" body="Leave the layout as it is." />}
            <OptionCard name="formatting" checked={selection.formatting === 'FORMAT'} onSelect={() => set({ formatting: 'FORMAT' })} title="APA, Harvard or another style" body="Headings, spacing, page numbers. Wording untouched." disabledReason={pdfReason} />
            <OptionCard name="formatting" checked={selection.formatting === 'TEMPLATE_FORMAT'} onSelect={() => set({ formatting: 'TEMPLATE_FORMAT' })} title="My university's guide" body="Upload your department's formatting guide. PaperAid reads it with AI, so it is priced separately." badge={badgeFor('TEMPLATE_FORMAT')} disabledReason={reasonFor('TEMPLATE_FORMAT', pdfReason)} />
          </div>
          {selection.formatting === 'FORMAT' && (
            <>
              <Select label="Style" className="mt-3" value={selection.preset} onChange={(e) => set({ preset: e.target.value })}>
                {config.presets.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.available}>
                    {p.label}
                  </option>
                ))}
              </Select>
              <CustomLayoutFields value={selection.custom ?? null} onChange={(custom) => set({ custom })} />
            </>
          )}
          {selection.formatting === 'TEMPLATE_FORMAT' && (
            <div className="mt-3">
              {guide?.meta ? (
                <FileChip name={guide.name} meta={fileMetaLine(guide.meta)} onRemove={() => setGuide(null)} />
              ) : (
                <FileDropzone compact label="Choose your guide" hint="DOCX or PDF" accept={ACCEPT} onFile={uploadGuide} />
              )}
              {guide?.error && <Alert tone="danger">{guide.error}</Alert>}
            </div>
          )}
          {selection.formatting !== 'NONE' && (
            <div className="mt-3">
              <Checkbox
                checked={!!selection.logo && selection.logo !== 'NONE'}
                onChange={(e) => set({ logo: e.target.checked ? 'CENTER' : 'NONE' })}
                label={<span className="font-semibold text-fg">Add an institution logo</span>}
              />
              {!!selection.logo && selection.logo !== 'NONE' && (
                <div className="mt-2 space-y-2">
                  {logo?.meta ? (
                    <FileChip name={logo.name} meta={`${logo.meta.format} · ${logo.meta.widthPx}×${logo.meta.heightPx}`} onRemove={() => setLogo(null)} />
                  ) : (
                    <FileDropzone compact label="Choose your logo" hint="PNG or JPEG · up to 2 MB" accept=".png,.jpg,.jpeg,image/png,image/jpeg" onFile={uploadLogo} />
                  )}
                  {logo?.error && <Alert tone="danger">{logo.error}</Alert>}
                  <Select label="Position" value={selection.logo} onChange={(e) => set({ logo: e.target.value as 'CENTER' | 'LEFT' })}>
                    <option value="CENTER">Top centre</option>
                    <option value="LEFT">Top left</option>
                  </Select>
                </div>
              )}
            </div>
          )}
          <Checkbox
            className="mt-3"
            checked={selection.latex}
            onChange={(e) => set({ latex: e.target.checked })}
            disabled={!!reasonFor('LATEX', pdfReason)}
            label={<span className="font-semibold text-fg">Also give me a LaTeX version</span>}
          />
        </div>
      )}

      {/* The price */}
      <div className="rounded-xl bg-surface-subtle p-3">
        {needsFile ? (
          <p className="text-sm text-fg-muted">{selection.formatting === 'TEMPLATE_FORMAT' && !guide?.meta ? 'Upload your guide to see the price.' : 'Upload your logo to see the price.'}</p>
        ) : pricing.loading ? (
          <Skeleton className="h-10 w-full" />
        ) : pricing.error ? (
          <Alert tone="warning" action={pricing.needsCredits ? <ButtonLink to="/app/credits" size="sm" variant="secondary">Your tokens</ButtonLink> : undefined}>
            {pricing.error}
          </Alert>
        ) : estimateRunning ? (
          <p className="flex items-center gap-2 text-sm font-semibold text-brand-900" aria-live="polite">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Sizing your paper&hellip; a minute or two.
          </p>
        ) : pricing.quote ? (
          <>
            <dl className="space-y-1 text-sm">
              {pricing.quote.lines.map((l) => (
                <div key={l.label} className="flex justify-between gap-3">
                  <dt className="text-fg-muted">{l.label}</dt>
                  <dd className="font-medium whitespace-nowrap">{formatTokens(l.amount)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 flex items-baseline justify-between border-t border-line pt-2">
              <span className="text-sm font-semibold">Price</span>
              <span className="text-xl font-bold">{formatTokens(pricing.quote.amount)}</span>
            </p>
            {!charging && <p className="mt-1 text-xs font-semibold text-brand-800">Not charged while PaperAid is in testing.</p>}
            {shortOfCredit && wallet && (
              <p className="mt-1 text-xs text-amber-800">
                Your balance is {formatTokens(wallet.available)}.{' '}
                <Link to="/app/credits" className="font-semibold underline">
                  Buy tokens
                </Link>
              </p>
            )}
          </>
        ) : pricing.feeCap !== null ? (
          <div>
            <p className="text-sm">{pricing.feeCap === 0 ? 'First, a free preview of how much would change.' : 'First, a short estimate of the work your paper needs.'}</p>
            <Button className="mt-2 w-full" variant="secondary" onClick={runEstimate}>
              {pricing.feeCap === 0 ? 'Preview my redraft' : 'Get my estimate'}
            </Button>
          </div>
        ) : null}
      </div>

      {mode === 'check' && (
        <p className="flex gap-2 text-xs leading-relaxed text-fg-subtle">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {DISCLAIMER}
        </p>
      )}
      <Checkbox checked={ownWork} onChange={(e) => setOwnWork(e.target.checked)} disabled={!pricing.quote} label="This is my own work, and I will check my institution's rules on AI-assisted editing." />
      {submitError && <Alert tone="danger">{submitError}</Alert>}
      <Button size="lg" className="w-full" disabled={!canStart} loading={submitting} onClick={start}>
        {text.start} <ArrowRight className="size-4" aria-hidden />
      </Button>
    </Card>
  )
}
