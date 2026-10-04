import { clsx } from 'clsx'
import { ArrowRight, Check, CheckCircle2, Info, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { Button, ButtonLink } from '../../components/ui/button'
import { Checkbox, Select } from '../../components/ui/field'
import { FileChip, FileDropzone, fileMetaLine } from '../../components/ui/file-dropzone'
import { Alert, Badge, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatTokens } from '../../lib/format'
import { AVAILABILITY_BADGE, INVITE_ONLY_REASON, NOT_CONFIGURED_REASON, SERVICES, STYLE_OPTIONS } from '../../lib/services'
import type { CustomLayout, EstimateView, FileMeta, FileRole, ImageMeta, Quote, ServiceId, ServiceSelection } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useWallet, walletChanged } from '../../lib/use-wallet'
import { useAuth } from '../auth/auth-context'
import { DISCLAIMER } from '../results/report'
import { QuickUpload } from '../studio/studio'
import { jobType, ServiceChooser, type JobType } from './service-chooser'

interface Upload {
  name: string
  progress: number
  meta: FileMeta | null
  error: string | null
}

const INITIAL: ServiceSelection = { writing: 'REFINE', intensity: 'STANDARD', style: 'PRESERVE_VOICE', sourceCheck: false, formatting: 'NONE', preset: 'apa7', latex: false, proposal: 'NONE', level: 'MASTERS' }
const REVIEW: ServiceSelection = { ...INITIAL, writing: 'NONE', proposal: 'REVIEW' }
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

const FONTS = ['Times New Roman', 'Calibri', 'Arial', 'Trebuchet MS', 'Georgia', 'Cambria', 'Garamond', 'Book Antiqua']

/** The student's own settings over the chosen style; "Style default" keeps the style's value. */
function CustomLayoutFields({ value, onChange }: { value: CustomLayout | null; onChange: (v: CustomLayout | null) => void }) {
  const [open, setOpen] = useState(!!value)
  const set = (patch: Partial<CustomLayout>) => {
    const next = { ...(value ?? {}), ...patch }
    onChange(Object.values(next).some((v) => v !== null && v !== undefined) ? next : null)
  }
  const num = (v: string) => (v ? Number(v) : null)
  if (!open)
    return (
      <button type="button" className="mt-3 text-sm font-medium text-brand-700 hover:underline" onClick={() => setOpen(true)}>
        Customise font, size, spacing or margins
      </button>
    )
  return (
    <div className="mt-3 grid gap-3 rounded-xl bg-surface-subtle p-4 sm:grid-cols-2">
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

function Step({ n, title, description, children, disabled }: { n: number; title: string; description?: string; children: ReactNode; disabled?: boolean }) {
  return (
    <section className={clsx('rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6', disabled && 'opacity-60')} aria-disabled={disabled}>
      <div className="mb-5 flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-700 text-sm font-semibold text-white">{n}</span>
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

/** New job: first choose what PaperAid will do (the chooser), then upload for that job. A draft
 *  being resumed goes straight to the form. The chosen job stays in the address. */
export function NewJobPage() {
  const [params] = useSearchParams()
  const type = jobType(params.get('service') ?? (params.get('review') ? 'PROPOSAL_REVIEW' : null))
  const draft = params.get('draft')
  const review = type?.id === 'PROPOSAL_REVIEW'
  // Every other job: upload, and the paper opens on its own page with the next step beside it.
  if (draft && !review) return <Navigate to={`/app/jobs/${draft}`} replace />
  if (!type && !draft) return <ServiceChooser />
  if (type && !review) return <QuickUpload key={type.id} type={type} />
  return <NewJobForm key={type?.id ?? 'draft'} type={type} />
}

function NewJobForm({ type }: { type: JobType | null }) {
  useTitle(type ? `New job: ${type.name}` : 'New paper job')
  const data = useData()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { config } = data
  const [params, setParams] = useSearchParams()
  const resumeId = params.get('draft')
  const keep: Record<string, string> = type ? { service: type.id } : {} // the chosen job stays in the address
  const [draftId, setDraftId] = useState<string | null>(null)
  // One draft per visit, created on the first upload and shared by concurrent uploads. Creating it
  // on mount let React (and token refreshes) create several, so an upload and its quote could land
  // on different drafts. The draft's id goes in the address, so a refresh resumes it.
  const draftPromise = useRef<Promise<string> | null>(null)
  const ensureDraft = () => {
    draftPromise.current ??= data.createDraft().then((id) => {
      setDraftId(id)
      setParams({ draft: id, ...keep }, { replace: true })
      return id
    })
    return draftPromise.current
  }
  const [source, setSource] = useState<Upload | null>(null)
  const [guide, setGuide] = useState<Upload | null>(null)
  const [logo, setLogo] = useState<{ name: string; meta: ImageMeta | null; error: string | null } | null>(null)
  const [selection, setSelection] = useState<ServiceSelection>(type?.selection ? { ...INITIAL, ...type.selection } : INITIAL)
  const review = selection.proposal === 'REVIEW'
  const fixing = selection.onlyBlocks?.length ?? 0
  const [restoring, setRestoring] = useState(!!resumeId)
  const [resumeError, setResumeError] = useState<string | null>(null)

  // Resume a draft from the address: its files and chosen services come back from the server, and
  // pricing below picks up its quote or its running estimate.
  useEffect(() => {
    if (!resumeId || draftPromise.current) return // this visit's own draft is already loaded
    let cancelled = false
    data
      .getJob(resumeId)
      .then((job) => {
        if (cancelled) return
        if (!job) {
          setResumeError('That draft is no longer available. Upload your paper to start again.')
          setParams(keep, { replace: true })
          return
        }
        if (job.status !== 'DRAFT' && job.status !== 'QUOTED') return navigate(`/app/jobs/${job.id}`, { replace: true })
        draftPromise.current = Promise.resolve(job.id)
        setDraftId(job.id)
        if (job.source) setSource({ name: job.source.name, progress: 100, meta: job.source, error: null })
        if (job.guideline) setGuide({ name: job.guideline.name, progress: 100, meta: job.guideline, error: null })
        if (job.logo) setLogo({ name: job.logo.name, meta: job.logo, error: null })
        if (job.quote || job.estimate || job.selection.onlyBlocks?.length) setSelection(job.selection)
      })
      .catch((e: unknown) => !cancelled && setResumeError(e instanceof DataError ? e.message : 'We could not load your draft. Refresh to try again.'))
      .finally(() => !cancelled && setRestoring(false))
    return () => {
      cancelled = true
    }
  }, [data, resumeId, navigate, setParams])
  const [pricing, setPricing] = useState<Pricing>(NO_PRICE)
  const { wallet } = useWallet()
  const [ownWork, setOwnWork] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const meta = source?.meta ?? null
  const guideMeta = guide?.meta ?? null
  const logoMeta = logo?.meta ?? null
  const needsGuide = (selection.formatting === 'TEMPLATE_FORMAT' && !guideMeta) || (selection.logo !== undefined && selection.logo !== 'NONE' && !logoMeta)
  const isPdf = meta?.format === 'PDF'
  const soon = (id: ServiceId) => config.availability[id] !== 'available'
  const badgeFor = (id: ServiceId) => {
    const availability = config.availability[id]
    return availability === 'available' ? undefined : <Badge>{AVAILABILITY_BADGE[availability]}</Badge>
  }
  const reasonFor = (id: ServiceId, otherwise?: string) =>
    config.availability[id] === 'soon'
      ? SERVICES[id].short
      : config.availability[id] === 'not_configured'
        ? NOT_CONFIGURED_REASON
        : config.availability[id] === 'invite_only'
          ? INVITE_ONLY_REASON
          : otherwise

  // Never leave the user on a choice they can't have: PDFs support AI Check only, and a service
  // that is unavailable on this server falls back to none.
  useEffect(() => {
    const ok = (id: ServiceId) => config.availability[id] === 'available'
    if (review) return // a proposal review runs on its own
    let writing = selection.writing
    let formatting = selection.formatting
    if (isPdf) {
      writing = ok('AI_CHECK') ? 'AI_CHECK' : 'NONE'
      formatting = 'NONE'
    }
    if (writing !== 'NONE' && !ok(writing)) writing = 'NONE'
    if (formatting !== 'NONE' && !ok(formatting)) formatting = 'NONE'
    // The source check comes with AI Check or Check + Refine only.
    const sourceCheck = selection.sourceCheck && (writing === 'AI_CHECK' || writing === 'REFINE' || writing === 'REDRAFT') && ok('SOURCE_CHECK')
    const latex = selection.latex && !isPdf && ok('LATEX') // LaTeX needs the Word file
    if (writing !== selection.writing || formatting !== selection.formatting || sourceCheck !== selection.sourceCheck || latex !== selection.latex)
      setSelection((s) => ({ ...s, writing, formatting, sourceCheck, latex }))
  }, [config.availability, isPdf, review, selection.writing, selection.formatting, selection.sourceCheck, selection.latex])

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
    // guideMeta / logoMeta: a new file clears the server's quote, so it must be priced again
  }, [data, draftId, meta, guideMeta, logoMeta, needsGuide, selection])

  // While the estimate runs on the server, watch the draft until it is priced (or fails).
  const estimateRunning = pricing.estimate?.status === 'RUNNING'
  useEffect(() => {
    if (!draftId || !estimateRunning) return
    let stop = () => {}
    stop = data.watchJob(
      draftId,
      (job) => {
        if (!job || job.estimate?.status === 'RUNNING') return
        stop()
        setPricing((p) => ({ ...p, estimate: job.estimate, quote: job.estimate?.status === 'READY' ? job.quote : null }))
        walletChanged()
      },
      // Refused while watching (signed out, or the browser could not be verified): show it rather
      // than an endless "Sizing your paper" (Codex audit 2026-09-28 #15). Refreshing resumes the draft.
      (message) => setPricing((p) => ({ ...p, estimate: null, error: `${message} Your estimate keeps running; refresh the page to see it.` })),
    )
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

  const uploadLogo = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (!['png', 'jpg', 'jpeg'].includes(ext ?? '')) return setLogo({ name: file.name, meta: null, error: 'Upload the logo as a PNG or JPEG image.' })
    setLogo({ name: file.name, meta: null, error: null })
    try {
      const id = await ensureDraft()
      setLogo({ name: file.name, meta: await data.uploadLogo(id, file), error: null })
    } catch (e) {
      setLogo({ name: file.name, meta: null, error: e instanceof DataError ? e.message : 'The logo could not be uploaded. Try again.' })
    }
  }
  const removeLogo = async () => {
    if (draftId && logo?.meta) await data.removeLogo(draftId).catch(() => undefined)
    setLogo(null)
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
  const pdfReason = isPdf ? 'Needs a Word file — a PDF can be checked only.' : undefined
  const chosen: ServiceId[] = [
    ...(selection.writing !== 'NONE' ? [selection.writing] : []),
    ...(selection.formatting !== 'NONE' ? [selection.formatting] : []),
    ...(selection.sourceCheck ? (['SOURCE_CHECK'] as const) : []),
    ...(selection.latex ? (['LATEX'] as const) : []),
    ...(review ? (['PROPOSAL'] as const) : []),
  ]
  const hold = pricing.quote ? pricing.quote.amount - pricing.quote.paid : 0
  const charging = config.creditsEnabled
  const fixedPrice = pricing.quote?.pricingVersion === 'fixed-v1'
  const shortOfCredit = charging && !!wallet && !!pricing.quote && wallet.available < hold
  const canSubmit = !!meta && !needsGuide && !!pricing.quote && ownWork && !pricing.loading && !shortOfCredit

  if (restoring)
    return (
      <>
        <PageHeader title="New paper job" description="Loading your draft…" />
        <Skeleton className="h-64 rounded-2xl" />
      </>
    )

  return (
    <>
      <PageHeader
        title={type ? type.name : 'New paper job'}
        description={
          type ? (
            <>
              {type.short}{' '}
              <Link to="/app/new" className="font-semibold text-brand-700 hover:underline">
                Choose a different job
              </Link>
            </>
          ) : (
            'Upload your paper, choose the work, and see your price before anything starts.'
          )
        }
      />
      {resumeError && (
        <Alert tone="warning" className="mb-5">
          {resumeError}
        </Alert>
      )}
      {user && !user.emailVerified && (
        <Alert tone="warning" className="mb-5" title="Verify your email first">
          We sent a verification link to {user.email}. Open it, then refresh this page to start a job.
        </Alert>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-5">
          <Step n={1} title="Your paper" description="Word (.docx) works with every service. A text-based PDF can be checked.">
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
                Have your institution’s formatting guide? Choose <strong>University templates</strong> below and upload it there.
              </p>
            )}
          </Step>

          <Step n={2} title="Choose the work" description="Pick one writing service and, if you like, formatting." disabled={!meta}>
            <div className="mb-6 rounded-xl border border-line p-4">
              <Checkbox
                checked={review}
                disabled={!meta || estimateRunning || !!reasonFor('PROPOSAL')}
                onChange={(e) => setSelection(e.target.checked ? { ...REVIEW, level: selection.level } : INITIAL)}
                label={
                  <>
                    <span className="font-semibold text-fg">This is a research proposal: review it</span> {badgeFor('PROPOSAL')}
                    <span className="mt-0.5 block text-xs">
                      {reasonFor('PROPOSAL') ??
                        'Missing sections, objective and question alignment, tense, references, length for your level, and what a supervisor is likely to raise. Your proposal is not changed.'}
                    </span>
                  </>
                }
              />
              {review && (
                <Select label="Level" className="mt-3 max-w-xs" value={selection.level} onChange={(e) => set({ level: e.target.value as ServiceSelection['level'] })}>
                  <option value="BACHELORS">Bachelor&rsquo;s (10&ndash;20 pages)</option>
                  <option value="PGD">Postgraduate Diploma (15&ndash;30 pages)</option>
                  <option value="MASTERS">Master&rsquo;s (15&ndash;30 pages)</option>
                  <option value="PHD">PhD (25&ndash;45 pages)</option>
                </Select>
              )}
            </div>
            <fieldset disabled={!meta || estimateRunning || review} className={review ? 'min-w-0 opacity-50' : 'min-w-0'}>
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

              {fixing > 0 && (
                <Alert tone="info" className="mt-4" title={`Fixing ${fixing} passage${fixing === 1 ? '' : 's'} you chose`}>
                  PaperAid rewrites only these passages, guided by their findings, in your voice. Everything else stays exactly as you wrote it.
                </Alert>
              )}

              {selection.writing !== 'NONE' && (
                <div className="mt-4 rounded-xl border border-line p-4">
                  <p className="text-sm font-semibold">Is this academic or research work?</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <OptionCard name="academic" checked={selection.academic !== false} onSelect={() => set({ academic: true })} title="Yes" body="Also checks academic writing, evidence and claims, methods and references." />
                    <OptionCard name="academic" checked={selection.academic === false} onSelect={() => set({ academic: false })} title="No" body="Focuses on writing patterns, clarity and structure." />
                  </div>
                </div>
              )}

              {selection.writing === 'REDRAFT' && (
                <div className="mt-4 rounded-xl bg-surface-subtle p-4">
                  <p className="text-sm font-semibold">What Deep Redraft changes</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-fg-muted">
                    <li>Paragraphs within each section may be reordered, merged, split and rewritten so your argument reads clearly.</li>
                    <li>Every claim keeps its strength, and your evidence, citations, quotations and figures stay exactly as they are.</li>
                    <li>Nothing moves between sections, and nothing new is added. Headings, lists and tables are not touched.</li>
                    <li>Much more of your paper will change than with Check + Refine, and every change is listed in the change report.</li>
                  </ul>
                  <p className="mt-5 text-sm font-semibold">Writing style</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {STYLE_OPTIONS.map((s) => (
                      <OptionCard key={s.id} name="style" checked={selection.style === s.id} onSelect={() => set({ style: s.id })} title={s.title} body={s.body} />
                    ))}
                  </div>
                </div>
              )}

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
                  <p className="mt-5 text-sm font-semibold">Writing style</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {STYLE_OPTIONS.map((s) => (
                      <OptionCard key={s.id} name="style" checked={selection.style === s.id} onSelect={() => set({ style: s.id })} title={s.title} body={s.body} />
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-fg-muted">No style adds facts, sources or detail, or makes a claim stronger than you made it.</p>
                </div>
              )}

              {(selection.writing === 'AI_CHECK' || selection.writing === 'REFINE' || selection.writing === 'REDRAFT') && (
                <div className="mt-4 rounded-xl border border-line p-4">
                  <Checkbox
                    checked={selection.sourceCheck}
                    onChange={(e) => set({ sourceCheck: e.target.checked })}
                    disabled={!!reasonFor('SOURCE_CHECK')}
                    label={
                      <>
                        <span className="font-semibold text-fg">Check my claims against live sources</span> {badgeFor('SOURCE_CHECK')}
                        <span className="mt-0.5 block text-xs">
                          {reasonFor('SOURCE_CHECK') ??
                            'We find the key factual claims in your paper and check each against current sources. Your paper is not changed.'}
                        </span>
                      </>
                    }
                  />
                </div>
              )}
            </fieldset>
            <fieldset disabled={!meta || estimateRunning || review} className={review ? 'mt-7 min-w-0 opacity-50' : 'mt-7 min-w-0'}>
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
                <>
                  <Select label="Formatting style" className="mt-4 max-w-sm" value={selection.preset} onChange={(e) => set({ preset: e.target.value })} hint="Sets page layout, headings, spacing and page numbers. It does not convert your citation style.">
                    {config.presets.map((p) => (
                      <option key={p.id} value={p.id} disabled={!p.available}>
                        {p.label}
                      </option>
                    ))}
                  </Select>
                  <CustomLayoutFields value={selection.custom ?? null} onChange={(custom) => set({ custom })} />
                </>
              )}
              {selection.formatting !== 'NONE' && (
                <div className="mt-4 rounded-xl border border-line p-4">
                  <Checkbox
                    checked={selection.logo !== undefined && selection.logo !== 'NONE'}
                    onChange={(e) => set({ logo: e.target.checked ? 'CENTER' : 'NONE' })}
                    label={
                      <>
                        <span className="font-semibold text-fg">Add an institution logo</span>
                        <span className="mt-0.5 block text-xs">Placed at the top of the first page and sized to fit. PNG or JPEG, up to 2 MB.</span>
                      </>
                    }
                  />
                  {selection.logo !== undefined && selection.logo !== 'NONE' && (
                    <div className="mt-3 space-y-3">
                      {logo?.meta ? (
                        <FileChip name={logo.name} meta={`${logo.meta.format} · ${logo.meta.widthPx}×${logo.meta.heightPx}`} onRemove={removeLogo} />
                      ) : (
                        <FileDropzone compact label="Choose your logo" hint="PNG or JPEG · up to 2 MB" accept=".png,.jpg,.jpeg,image/png,image/jpeg" onFile={uploadLogo} />
                      )}
                      {logo?.error && <Alert tone="danger">{logo.error}</Alert>}
                      <Select label="Position" className="max-w-xs" value={selection.logo} onChange={(e) => set({ logo: e.target.value as 'CENTER' | 'LEFT' })}>
                        <option value="CENTER">Top centre</option>
                        <option value="LEFT">Top left</option>
                      </Select>
                    </div>
                  )}
                </div>
              )}
              <div className="mt-4 rounded-xl border border-line p-4">
                <Checkbox
                  checked={selection.latex}
                  onChange={(e) => set({ latex: e.target.checked })}
                  disabled={!!reasonFor('LATEX', pdfReason)}
                  label={
                    <>
                      <span className="font-semibold text-fg">Also convert to LaTeX</span> {badgeFor('LATEX')}
                      <span className="mt-0.5 block text-xs">
                        {reasonFor('LATEX', pdfReason) ??
                          'A LaTeX project (.tex, figures and a compiled PDF when possible) of your finished paper. Citations and references stay exactly as written.'}
                      </span>
                    </>
                  }
                />
              </div>
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
                    {formatTokens(wallet.available)}
                  </Link>
                </p>
              )}
              {!meta ? (
                <p className="text-sm text-fg-muted">Upload your paper to see the price. It depends on the work your paper needs.</p>
              ) : needsGuide ? (
                <p className="text-sm text-fg-muted">{selection.formatting === 'TEMPLATE_FORMAT' && !guideMeta ? 'Upload your formatting guide to see the price.' : 'Upload your logo to see the price.'}</p>
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
                    {charging && ` Up to ${formatTokens(pricing.estimate.feeCap)} is held; you pay only what the scan actually costs.`}
                  </p>
                </div>
              ) : pricing.quote ? (
                <>
                  <dl className="space-y-2 text-sm">
                    {pricing.quote.lines.map((l) => (
                      <div key={l.label} className="flex justify-between gap-4">
                        <dt className="text-fg-muted">{l.label}</dt>
                        <dd className="font-medium whitespace-nowrap">{formatTokens(l.amount)}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-4 flex items-baseline justify-between border-t border-line pt-4">
                    <span className="text-sm font-semibold">{fixedPrice ? 'Price' : charging ? 'Most you’ll pay' : 'Most it would cost'}</span>
                    <span className="text-right">
                      <span className="block text-2xl font-medium tracking-tight">{formatTokens(pricing.quote.amount)}</span>
                    </span>
                  </div>
                  {selection.writing === 'REDRAFT' && pricing.estimate?.intervention != null && (
                    <p className="mt-3 rounded-lg bg-surface-subtle px-3 py-2 text-sm">
                      Estimated change: <strong>about {Math.round(pricing.estimate.intervention * 100)}% of your paper</strong> will be rewritten.
                    </p>
                  )}
                  {pricing.quote.paid > 0 && (
                    <p className="mt-2 flex justify-between text-sm text-fg-muted">
                      <span>Already paid (estimate)</span> <span>{formatTokens(pricing.quote.paid)}</span>
                    </p>
                  )}
                  {charging ? (
                    <>
                      <p className="mt-1 flex justify-between text-sm font-semibold">
                        <span>Held from your credits now</span> <span>{formatTokens(hold)}</span>
                      </p>
                      <p className="mt-2 text-xs leading-relaxed text-fg-subtle">
                        {fixedPrice
                          ? 'This is the price. If part of the job can’t be delivered, you pay only for the part that was. Valid for 30 minutes.'
                          : 'You’re charged for the work actually done, never more than this, and the rest returns to your balance. Valid for 30 minutes.'}
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
                      This needs {formatTokens(hold)} and your balance is {formatTokens(wallet.available)}.
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
                  <p className="text-sm font-semibold">{pricing.feeCap === 0 ? 'First, a free preview' : 'First, a short AI estimate'}</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">
                    {pricing.feeCap === 0 ? (
                      'PaperAid reads your paper and plans the redraft, so you can see how much of it would change and the price before you decide. It takes a minute or two and costs nothing.'
                    ) : (
                      <>
                        Refinement is priced from the work your paper actually needs. PaperAid scans it and drafts a plan
                        {charging ? (
                          <>
                            ; the scan costs at most <strong className="text-fg">{formatTokens(pricing.feeCap)}</strong> and counts toward your job if you go ahead.
                          </>
                        ) : (
                          '. It takes a minute or two and is not charged while PaperAid is in testing.'
                        )}
                      </>
                    )}
                  </p>
                  <Button className="mt-4 w-full" onClick={runEstimate} disabled={charging && !!wallet && wallet.available < pricing.feeCap}>
                    {pricing.feeCap === 0 ? 'Preview my redraft' : charging ? <>Get my estimate &middot; up to {formatTokens(pricing.feeCap)}</> : 'Get my estimate'}
                  </Button>
                  {charging && wallet && wallet.available < pricing.feeCap && (
                    <p className="mt-2 text-xs text-amber-800">
                      Your balance is {formatTokens(wallet.available)}.{' '}
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
                {pricing.quote && charging ? `Start job · hold ${formatTokens(hold)}` : 'Start job'} <ArrowRight className="size-4" aria-hidden />
              </Button>
            </div>
          </Card>
        </aside>
      </div>
    </>
  )
}
