import { clsx } from 'clsx'
import { ArrowRight, Check, CheckCircle2, Info, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Checkbox, Select } from '../../components/ui/field'
import { FileChip, FileDropzone, fileMetaLine } from '../../components/ui/file-dropzone'
import { Alert, Badge, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatUGX, formatUSDFromUGX } from '../../lib/format'
import { AVAILABILITY_BADGE, NOT_CONFIGURED_REASON, SERVICES } from '../../lib/services'
import type { EstimateView, FileMeta, FileRole, Quote, ServiceId, ServiceSelection } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useWallet, walletChanged } from '../../lib/use-wallet'
import { useAuth } from '../auth/auth-context'
import { DISCLAIMER } from '../results/report'

interface Upload {
  name: string
  progress: number
  meta: FileMeta | null
  error: string | null
}

const INITIAL: ServiceSelection = { writing: 'REFINE', intensity: 'STANDARD', formatting: 'NONE', preset: 'apa7', latex: false }
const ACCEPT = '.docx,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf'

// What the price panel shows. Refinement is priced after a paid AI estimate that the student
// starts deliberately (feeCap is its most); everything else is priced from length at once.
interface Pricing {
  quote: Quote | null
  feeCap: number | null
  estimate: EstimateView | null
  loading: boolean
  error: string | null
  needsCredits: boolean
}

const NO_PRICE: Pricing = { quote: null, feeCap: null, estimate: null, loading: false, error: null, needsCredits: false }

function priceError(e: unknown): Pick<Pricing, 'error' | 'needsCredits'> {
  return { error: e instanceof DataError ? e.message : 'We could not price this job.', needsCredits: e instanceof DataError && e.status === 402 }
}

function Step({ n, title, description, children, disabled }: { n: number; title: string; description?: string; children: ReactNode; disabled?: boolean }) {
  return (
    <section className={clsx('rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6', disabled && 'opacity-60')} aria-disabled={disabled}>
      <div className="mb-5 flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-700 text-sm font-bold text-white">{n}</span>
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-fg-muted">{description}</p>}
        </div>
      </div>
      {children}
    </section>
  )
}

interface OptionCardProps {
  name: string
  checked: boolean
  onSelect: () => void
  title: string
  body: string
  badge?: ReactNode
  disabledReason?: string
}

function OptionCard({ name, checked, onSelect, title, body, badge, disabledReason }: OptionCardProps) {
  const disabled = !!disabledReason
  return (
    <label
      className={clsx(
        'relative flex cursor-pointer gap-3 rounded-xl border p-4 transition-colors',
        checked ? 'border-brand-500 bg-brand-50/60 ring-1 ring-brand-500' : 'border-line hover:border-brand-300',
        disabled && 'cursor-not-allowed bg-surface-subtle hover:border-line',
      )}
    >
      <input type="radio" name={name} checked={checked} disabled={disabled} onChange={onSelect} className="sr-only" />
      <span
        aria-hidden
        className={clsx('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2', checked ? 'border-brand-600 bg-brand-600' : 'border-line-strong bg-white')}
      >
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

export function NewJobPage() {
  useTitle('New paper job')
  const data = useData()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { config } = data
  const [draftId, setDraftId] = useState<string | null>(null)
  // One draft per visit, created on the first upload and shared by concurrent uploads. Creating it
  // on mount let React (and token refreshes) create several, so an upload and its quote could land
  // on different drafts.
  const draftPromise = useRef<Promise<string> | null>(null)
  const ensureDraft = () => {
    draftPromise.current ??= data.createDraft().then((id) => {
      setDraftId(id)
      return id
    })
    return draftPromise.current
  }
  const [source, setSource] = useState<Upload | null>(null)
  const [guide, setGuide] = useState<Upload | null>(null)
  const [selection, setSelection] = useState<ServiceSelection>(INITIAL)
  const [pricing, setPricing] = useState<Pricing>(NO_PRICE)
  const { wallet } = useWallet()
  const [ownWork, setOwnWork] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const meta = source?.meta ?? null
  const guideMeta = guide?.meta ?? null
  const needsGuide = selection.formatting === 'TEMPLATE_FORMAT' && !guideMeta
  const isPdf = meta?.format === 'PDF'
  const soon = (id: ServiceId) => config.availability[id] !== 'available'
  const badgeFor = (id: ServiceId) => {
    const availability = config.availability[id]
    return availability === 'available' ? undefined : <Badge>{AVAILABILITY_BADGE[availability]}</Badge>
  }
  const reasonFor = (id: ServiceId, otherwise?: string) =>
    config.availability[id] === 'soon' ? SERVICES[id].short : config.availability[id] === 'not_configured' ? NOT_CONFIGURED_REASON : otherwise

  // Never leave the user on a choice they can't have: PDFs support AI Check only, and a service
  // that is unavailable on this server falls back to none.
  useEffect(() => {
    const ok = (id: ServiceId) => config.availability[id] === 'available'
    let writing = selection.writing
    let formatting = selection.formatting
    if (isPdf) {
      writing = ok('AI_CHECK') ? 'AI_CHECK' : 'NONE'
      formatting = 'NONE'
    }
    if (writing !== 'NONE' && !ok(writing)) writing = 'NONE'
    if (formatting !== 'NONE' && !ok(formatting)) formatting = 'NONE'
    if (writing !== selection.writing || formatting !== selection.formatting) setSelection((s) => ({ ...s, writing, formatting }))
  }, [config.availability, isPdf, selection.writing, selection.formatting])

  useEffect(() => {
    if (!draftId || !meta) return
    if (needsGuide) {
      setPricing(NO_PRICE)
      return
    }
    let cancelled = false
    setPricing({ ...NO_PRICE, loading: true })
    const timer = setTimeout(() => {
      data
        .requestQuote(draftId, selection) // never starts a paid estimate: that takes the student's click
        .then((r) => !cancelled && setPricing({ ...NO_PRICE, quote: r.quote, feeCap: r.estimateFeeCap, estimate: r.estimate }))
        .catch((e: unknown) => !cancelled && setPricing({ ...NO_PRICE, ...priceError(e) }))
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // guideMeta: a new guide clears the server's quote, so it must be priced again
  }, [data, draftId, meta, guideMeta, needsGuide, selection])

  // While the estimate runs on the server, watch the draft until it is priced (or fails).
  const estimateRunning = pricing.estimate?.status === 'RUNNING'
  useEffect(() => {
    if (!draftId || !estimateRunning) return
    let stop = () => {}
    stop = data.watchJob(draftId, (job) => {
      if (!job || job.estimate?.status === 'RUNNING') return
      stop()
      setPricing((p) => ({ ...p, estimate: job.estimate, quote: job.estimate?.status === 'READY' ? job.quote : null }))
      walletChanged()
    })
    return () => stop()
  }, [data, draftId, estimateRunning])

  const runEstimate = async () => {
    if (!draftId) return
    setPricing((p) => ({ ...p, loading: true, error: null, needsCredits: false }))
    try {
      const r = await data.requestQuote(draftId, selection, true)
      setPricing({ ...NO_PRICE, quote: r.quote, feeCap: r.estimateFeeCap, estimate: r.estimate })
      walletChanged()
    } catch (e) {
      setPricing((p) => ({ ...p, loading: false, ...priceError(e) }))
    }
  }

  const upload = async (role: FileRole, file: File) => {
    const setUpload = role === 'source' ? setSource : setGuide
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext !== 'docx' && ext !== 'pdf') {
      setUpload({ name: file.name, progress: 100, meta: null, error: 'Upload a Word document (.docx) or a text-based PDF.' })
      return
    }
    setUpload({ name: file.name, progress: 0, meta: null, error: null })
    try {
      const id = await ensureDraft()
      const result = await data.uploadFile(id, role, file, (progress) => setUpload((u) => u && { ...u, progress }))
      setUpload({ name: file.name, progress: 100, meta: result, error: null })
    } catch (e) {
      if (!draftId) draftPromise.current = null // creating the draft itself failed: allow a fresh attempt
      setUpload({ name: file.name, progress: 100, meta: null, error: e instanceof DataError ? e.message : 'Upload failed. Try again.' })
    }
  }

  const removeGuide = async () => {
    if (!guide) return
    if (draftId && guide.meta) {
      try {
        await data.removeGuideline(draftId)
      } catch (e) {
        setGuide({ ...guide, error: e instanceof DataError ? e.message : 'We could not remove the guide. Try again.' })
        return
      }
    }
    setGuide(null)
  }

  const submit = async () => {
    if (!draftId || !pricing.quote) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const jobId = await data.submitJob(draftId, pricing.quote.id)
      walletChanged()
      navigate(`/app/jobs/${jobId}`)
    } catch (e) {
      setSubmitError(e instanceof DataError ? e.message : 'We could not start this job. Try again.')
      setSubmitting(false)
    }
  }

  const set = (patch: Partial<ServiceSelection>) => setSelection((s) => ({ ...s, ...patch }))
  const pdfReason = isPdf ? 'Needs a Word file — PDFs support AI Check only.' : undefined
  const chosen: ServiceId[] = [
    ...(selection.writing !== 'NONE' ? [selection.writing] : []),
    ...(selection.formatting !== 'NONE' ? [selection.formatting] : []),
  ]
  const hold = pricing.quote ? pricing.quote.amount - pricing.quote.paid : 0
  const charging = config.creditsEnabled
  const shortOfCredit = charging && !!wallet && !!pricing.quote && wallet.available < hold
  const canSubmit = !!meta && !needsGuide && !!pricing.quote && ownWork && !pricing.loading && !shortOfCredit
  const rate = wallet?.ugxPerUsd ?? config.ugxPerUsd

  return (
    <>
      <PageHeader title="New paper job" description="Upload your paper, choose the work, and see your price before anything starts." />
      {user && !user.emailVerified && (
        <Alert tone="warning" className="mb-5" title="Verify your email first">
          We sent a verification link to {user.email}. Open it, then refresh this page to start a job.
        </Alert>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <Step n={1} title="Your paper" description="Word (.docx) works with every service. Text-based PDFs work with AI Check.">
            {!source || source.error ? (
              <>
                <FileDropzone label="Choose your paper" hint="DOCX or PDF · up to 20 MB" accept={ACCEPT} onFile={(file) => upload('source', file)} />
                {source?.error && (
                  <Alert tone="danger" className="mt-3" title={`We can't use “${source.name}”`}>
                    {source.error}
                  </Alert>
                )}
              </>
            ) : (
              <div className="space-y-3">
                <FileChip name={source.name} progress={source.progress} meta={meta ? fileMetaLine(meta) : 'Checking your file…'} onRemove={() => setSource(null)} />
                {meta && (
                  <p className="flex items-center gap-2 text-sm text-brand-800">
                    <CheckCircle2 className="size-4 text-brand-600" aria-hidden /> Readable text found · {meta.headingCount} headings detected
                  </p>
                )}
              </div>
            )}
            {!soon('TEMPLATE_FORMAT') && (
              <p className="mt-4 rounded-lg bg-surface-subtle p-3 text-sm text-fg-muted">
                Have a university formatting guide? Choose <strong>University templates</strong> below and upload it there.
              </p>
            )}
          </Step>

          <Step n={2} title="Choose the work" description="Pick one writing service and, if you like, formatting." disabled={!meta}>
            <fieldset disabled={!meta || estimateRunning}>
              <legend className="mb-3 text-sm font-semibold text-fg">Writing</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <OptionCard name="writing" checked={selection.writing === 'AI_CHECK'} onSelect={() => set({ writing: 'AI_CHECK' })} title={SERVICES.AI_CHECK.name} body="Report only — your document is not edited." badge={badgeFor('AI_CHECK')} disabledReason={reasonFor('AI_CHECK')} />
                <OptionCard
                  name="writing"
                  checked={selection.writing === 'REFINE'}
                  onSelect={() => set({ writing: 'REFINE' })}
                  title={SERVICES.REFINE.name}
                  body="Check, then refine flagged passages. Citations and numbers stay locked."
                  badge={badgeFor('REFINE') ?? <Badge tone="brand">Popular</Badge>}
                  disabledReason={reasonFor('REFINE', pdfReason)}
                />
                <OptionCard
                  name="writing"
                  checked={selection.writing === 'REDRAFT'}
                  onSelect={() => set({ writing: 'REDRAFT' })}
                  title={SERVICES.REDRAFT.name}
                  body={SERVICES.REDRAFT.short}
                  badge={badgeFor('REDRAFT')}
                  disabledReason={reasonFor('REDRAFT', pdfReason)}
                />
                <OptionCard name="writing" checked={selection.writing === 'NONE'} onSelect={() => set({ writing: 'NONE' })} title="No writing check" body="Formatting only." disabledReason={pdfReason} />
              </div>

              {selection.writing === 'REFINE' && (
                <div className="mt-4 rounded-xl bg-surface-subtle p-4">
                  <p className="text-sm font-semibold">How much should we refine?</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {(
                      [
                        ['LIGHT', 'Light', 'Only the clearest issues — up to about a quarter of the paper.'],
                        ['STANDARD', 'Standard', 'All flagged passages — up to about half of the paper.'],
                      ] as const
                    ).map(([id, title, body]) => (
                      <OptionCard key={id} name="intensity" checked={selection.intensity === id} onSelect={() => set({ intensity: id })} title={title} body={body} />
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-fg-muted">Refining more of the paper costs more because each passage is rewritten and independently checked.</p>
                </div>
              )}

            </fieldset>
            <fieldset disabled={!meta || estimateRunning} className="mt-7">
              <legend className="mb-3 text-sm font-semibold text-fg">Formatting</legend>
              <div className="grid gap-3 sm:grid-cols-3">
                <OptionCard name="formatting" checked={selection.formatting === 'NONE'} onSelect={() => set({ formatting: 'NONE' })} title="Keep my formatting" body="Leave the layout as it is." />
                <OptionCard
                  name="formatting"
                  checked={selection.formatting === 'FORMAT'}
                  onSelect={() => set({ formatting: 'FORMAT' })}
                  title={SERVICES.FORMAT.name}
                  body="APA or Harvard layout. Wording untouched."
                  disabledReason={pdfReason}
                />
                <OptionCard
                  name="formatting"
                  checked={selection.formatting === 'TEMPLATE_FORMAT'}
                  onSelect={() => set({ formatting: 'TEMPLATE_FORMAT' })}
                  title={SERVICES.TEMPLATE_FORMAT.name}
                  body="Follow your department's guide. Wording untouched."
                  badge={badgeFor('TEMPLATE_FORMAT')}
                  disabledReason={reasonFor('TEMPLATE_FORMAT', pdfReason)}
                />
              </div>
              {selection.formatting === 'TEMPLATE_FORMAT' && (
                <div className="mt-4 rounded-xl bg-surface-subtle p-4">
                  <p className="text-sm font-semibold">Your formatting guide</p>
                  <p className="mt-0.5 mb-3 text-xs text-fg-muted">
                    The department handbook or guideline document (DOCX or PDF). We find each rule in it and show you the sentence it came from.
                  </p>
                  {!guide || guide.error ? (
                    <>
                      <FileDropzone label="Choose your guide" hint="DOCX or PDF · up to 20 MB" accept={ACCEPT} onFile={(file) => upload('guideline', file)} />
                      {guide?.error && (
                        <Alert tone="danger" className="mt-3" title={`We can't use “${guide.name}”`}>
                          {guide.error}
                        </Alert>
                      )}
                    </>
                  ) : (
                    <FileChip name={guide.name} progress={guide.progress} meta={guideMeta ? fileMetaLine(guideMeta) : 'Checking your guide…'} onRemove={removeGuide} />
                  )}
                </div>
              )}
              {selection.formatting === 'FORMAT' && (
                <Select label="Formatting style" className="mt-4 max-w-sm" value={selection.preset} onChange={(e) => set({ preset: e.target.value })} hint="Sets page layout, headings, spacing and page numbers. It does not convert your citation style.">
                  {config.presets.map((p) => (
                    <option key={p.id} value={p.id} disabled={!p.available}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              )}
            </fieldset>
          </Step>
        </div>

        <aside className="lg:sticky lg:top-24">
          <Card className="overflow-hidden">
            <div className="border-b border-line bg-surface-subtle px-5 py-4">
              <h2 className="text-base font-semibold">3 · Your quote</h2>
            </div>
            <div className="p-5">
              {charging && meta && wallet && (
                <p className="mb-4 flex items-center justify-between rounded-lg bg-surface-subtle px-3 py-2 text-xs text-fg-muted">
                  <span>Your credits{wallet.testCredits && ' (test)'}</span>
                  <Link to="/app/credits" className="font-semibold text-fg hover:underline">
                    {formatUGX(wallet.available)}
                  </Link>
                </p>
              )}
              {!meta ? (
                <p className="text-sm text-fg-muted">Upload your paper to see the price. It depends on the work your paper needs.</p>
              ) : needsGuide ? (
                <p className="text-sm text-fg-muted">Upload your formatting guide to see the price.</p>
              ) : pricing.loading ? (
                <div className="space-y-3" aria-busy="true" aria-label="Calculating quote">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-8 w-1/2" />
                </div>
              ) : pricing.error ? (
                <Alert
                  tone="warning"
                  action={
                    pricing.needsCredits ? (
                      <ButtonLink to="/app/credits" size="sm" variant="secondary">
                        Your credits
                      </ButtonLink>
                    ) : undefined
                  }
                >
                  {pricing.error}
                </Alert>
              ) : estimateRunning && pricing.estimate ? (
                <div className="rounded-xl bg-brand-50 p-4 text-sm" aria-live="polite">
                  <p className="flex items-center gap-2 font-semibold text-brand-900">
                    <Loader2 className="size-4 animate-spin" aria-hidden /> Sizing your paper&hellip;
                  </p>
                  <p className="mt-1.5 leading-relaxed text-brand-800">
                    PaperAid&rsquo;s AI is reading your paper and drafting its plan. This takes a minute or two.
                    {charging && ` Up to ${formatUGX(pricing.estimate.feeCap)} is held; you pay only what the scan actually costs.`}
                  </p>
                </div>
              ) : pricing.quote ? (
                <>
                  <dl className="space-y-2 text-sm">
                    {pricing.quote.lines.map((l) => (
                      <div key={l.label} className="flex justify-between gap-4">
                        <dt className="text-fg-muted">{l.label}</dt>
                        <dd className="font-medium whitespace-nowrap">{formatUGX(l.amount)}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-4 flex items-baseline justify-between border-t border-line pt-4">
                    <span className="text-sm font-semibold">{charging ? 'Most you’ll pay' : 'Most it would cost'}</span>
                    <span className="text-right">
                      <span className="block text-2xl font-bold tracking-tight">{formatUGX(pricing.quote.amount)}</span>
                      <span className="text-xs text-fg-subtle">{formatUSDFromUGX(pricing.quote.amount, rate)}</span>
                    </span>
                  </div>
                  {pricing.quote.paid > 0 && (
                    <p className="mt-2 flex justify-between text-sm text-fg-muted">
                      <span>Already paid (estimate)</span> <span>{formatUGX(pricing.quote.paid)}</span>
                    </p>
                  )}
                  {charging ? (
                    <>
                      <p className="mt-1 flex justify-between text-sm font-semibold">
                        <span>Held from your credits now</span> <span>{formatUGX(hold)}</span>
                      </p>
                      <p className="mt-2 text-xs leading-relaxed text-fg-subtle">
                        You&rsquo;re charged for the work actually done, never more than this, and the rest returns to your balance. Valid for 30 minutes.
                      </p>
                    </>
                  ) : (
                    <p className="mt-2 rounded-lg bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-800">Not charged while PaperAid is in testing.</p>
                  )}
                  {shortOfCredit && wallet && (
                    <Alert
                      tone="warning"
                      className="mt-3"
                      action={
                        <ButtonLink to="/app/credits" size="sm" variant="secondary">
                          Your credits
                        </ButtonLink>
                      }
                    >
                      This needs {formatUGX(hold)} of credit and your balance is {formatUGX(wallet.available)}.
                    </Alert>
                  )}

                  <div className="mt-5 border-t border-line pt-4">
                    <p className="text-xs font-semibold tracking-wide text-fg-subtle uppercase">You&rsquo;ll receive</p>
                    <ul className="mt-2 space-y-1.5">
                      {chosen.flatMap((id) => SERVICES[id].youGet).map((item) => (
                        <li key={item} className="flex gap-2 text-sm text-fg-muted">
                          <Check className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : pricing.estimate?.status === 'FAILED' ? (
                <Alert
                  tone="warning"
                  title="The estimate didn't finish"
                  action={
                    <Button size="sm" variant="secondary" onClick={runEstimate}>
                      Try again
                    </Button>
                  }
                >
                  {pricing.estimate.message} It was not charged.
                </Alert>
              ) : pricing.feeCap !== null ? (
                <div>
                  <p className="text-sm font-semibold">First, a short AI estimate</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">
                    Refinement is priced from the work your paper actually needs. PaperAid&rsquo;s AI scans it and drafts a plan
                    {charging ? (
                      <>
                        ; the scan costs at most <strong className="text-fg">{formatUGX(pricing.feeCap)}</strong> and counts toward your job if you go ahead.
                      </>
                    ) : (
                      '. It takes a minute or two and is not charged while PaperAid is in testing.'
                    )}
                  </p>
                  <Button className="mt-4 w-full" onClick={runEstimate} disabled={charging && !!wallet && wallet.available < pricing.feeCap}>
                    {charging ? <>Get my estimate &middot; up to {formatUGX(pricing.feeCap)}</> : 'Get my estimate'}
                  </Button>
                  {charging && wallet && wallet.available < pricing.feeCap && (
                    <p className="mt-2 text-xs text-amber-800">
                      Your balance is {formatUGX(wallet.available)}.{' '}
                      <Link to="/app/credits" className="font-semibold underline">
                        See your credits
                      </Link>
                    </p>
                  )}
                </div>
              ) : null}

              {selection.writing !== 'NONE' && meta && (
                <p className="mt-4 flex gap-2 text-xs leading-relaxed text-fg-subtle">
                  <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {DISCLAIMER}
                </p>
              )}

              <Checkbox
                className="mt-5"
                checked={ownWork}
                onChange={(e) => setOwnWork(e.target.checked)}
                disabled={!pricing.quote}
                label="This is my own work, and I will check my institution's rules on AI-assisted editing."
              />
              {submitError && (
                <Alert tone="danger" className="mt-4">
                  {submitError}
                </Alert>
              )}
              <Button size="lg" className="mt-5 w-full" disabled={!canSubmit} loading={submitting} onClick={submit}>
                {pricing.quote && charging ? `Start job · hold ${formatUGX(hold)}` : 'Start job'} <ArrowRight className="size-4" aria-hidden />
              </Button>
            </div>
          </Card>
        </aside>
      </div>
    </>
  )
}
