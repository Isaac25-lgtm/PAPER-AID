import { clsx } from 'clsx'
import { CheckCircle2, FileText } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Alert, Card, PageHeader, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { Job, JobDocument } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useAuth } from '../auth/auth-context'
import type { JobType } from '../upload/service-chooser'
import { JobOptions, startingSelection, type Mode } from './options'

const ACCEPT = '.docx,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf'
const WORD_ONLY = '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document' // a PDF can only be checked

/** The step a chosen job starts with, once the paper is uploaded. Paper Check starts with the check
 *  while it is offered, otherwise with the redraft (owner decision 2026-10-07: the check is hidden). */
export function modeFor(service: string | null, checkOffered = true): Mode {
  if (service === 'REFINE' || service === 'REDRAFT') return 'redraft'
  if (service === 'ACADEMIC_FORMAT' || service === 'FORMAT' || service === 'TEMPLATE_FORMAT' || service === 'LATEX') return 'format'
  return checkOffered ? 'check' : 'redraft'
}

/** New job, step one: just the paper. It opens on its own page at once, with the next step beside it. */
export function QuickUpload({ type }: { type: JobType }) {
  useTitle(type.name)
  const data = useData()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [state, setState] = useState<{ name: string; progress: number; error: string | null } | null>(null)
  const checkOffered = data.config.availability.AI_CHECK === 'available'

  const upload = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext !== 'docx' && (ext !== 'pdf' || !checkOffered))
      return setState({ name: file.name, progress: 100, error: checkOffered ? 'Upload a Word document (.docx) or a text-based PDF.' : 'Upload a Word document (.docx).' })
    setState({ name: file.name, progress: 0, error: null })
    try {
      const id = await data.createDraft()
      await data.uploadFile(id, 'source', file, (progress) => setState((s) => s && { ...s, progress }))
      navigate(`/app/jobs/${id}?next=${modeFor(type.id, checkOffered)}&service=${type.id}`)
    } catch (e) {
      setState({ name: file.name, progress: 100, error: e instanceof DataError ? e.message : 'Upload failed. Try again.' })
    }
  }

  return (
    <>
      <PageHeader
        title={type.name}
        description={
          <>
            {type.short}{' '}
            <Link to="/app/new" className="font-semibold text-brand-700 hover:underline">
              Choose a different job
            </Link>
          </>
        }
      />
      {user && !user.emailVerified && (
        <Alert tone="warning" className="mb-5" title="Verify your email first">
          We sent a verification link to {user.email}. Open it, then refresh this page.
        </Alert>
      )}
      <Card className="mx-auto max-w-3xl p-6 sm:p-10">
        {state && !state.error ? (
          <div className="py-10 text-center" aria-live="polite">
            <FileText className="mx-auto size-8 text-brand-600" aria-hidden />
            <p className="mt-3 font-semibold">{state.name}</p>
            <p className="mt-1 text-sm text-fg-muted">{state.progress < 100 ? `Uploading… ${state.progress}%` : 'Opening your paper…'}</p>
          </div>
        ) : (
          <>
            <FileDropzone
              label="Choose your paper"
              hint={checkOffered ? 'Word (.docx) or a text-based PDF · up to 20 MB' : 'Word (.docx) · up to 20 MB'}
              accept={checkOffered ? ACCEPT : WORD_ONLY}
              onFile={upload}
            />
            {state?.error && (
              <Alert tone="danger" className="mt-4" title={`We can't use “${state.name}”`}>
                {state.error}
              </Alert>
            )}
            <p className="mt-4 text-center text-xs text-fg-subtle">Your paper opens on the next screen. Nothing runs, and nothing is charged, until you choose.</p>
          </>
        )}
      </Card>
    </>
  )
}

/** The paper as uploaded (or as last read), for the screens before results exist. */
export function PaperPreview({ jobId, dim, children }: { jobId: string; dim?: boolean; children?: ReactNode }) {
  const data = useData()
  const [doc, setDoc] = useState<JobDocument | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    data.workspace
      .document(jobId)
      .then((d) => !cancelled && setDoc(d))
      .catch((e: unknown) => !cancelled && setError(e instanceof DataError ? e.message : 'We could not show your paper.'))
    return () => {
      cancelled = true
    }
  }, [data, jobId])
  return (
    <Card className={clsx('min-w-0 p-5 sm:p-8 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto', dim && 'opacity-70')}>
      {children}
      {error ? (
        <Alert tone="warning">{error}</Alert>
      ) : !doc ? (
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <article className="space-y-3 font-serif text-[0.97rem] leading-relaxed text-fg" aria-label="Your paper">
          {doc.blocks.map((b) =>
            b.kind === 'heading' || b.kind === 'title' ? (
              <h3 key={b.id} className={clsx('pt-3 font-sans font-semibold', b.kind === 'title' ? 'text-xl' : (b.level ?? 1) <= 1 ? 'text-lg' : 'text-base')}>
                {b.text}
              </h3>
            ) : (
              <p key={b.id} className={clsx('whitespace-pre-line', (b.kind === 'reference' || b.kind === 'caption') && 'text-sm text-fg-muted')}>
                {b.text}
              </p>
            ),
          )}
        </article>
      )}
    </Card>
  )
}

/** A paper that has not been started: the paper on the left, the chosen step beside it. */
export function DraftStudio({ job }: { job: Job }) {
  const [params] = useSearchParams()
  const { config } = useData()
  const service = params.get('service')
  const prepared = (job.selection.onlyBlocks?.length ?? 0) > 0
  const checkOffered = config.availability.AI_CHECK === 'available'
  const asked = (params.get('next') as Mode | null) ?? modeFor(service, checkOffered)
  const mode: Mode = prepared ? 'prepared' : asked === 'check' && !checkOffered ? 'redraft' : asked
  const [initial] = useState(() => startingSelection(mode, job, service))
  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="order-2 lg:order-1">
        <PaperPreview jobId={job.id}>
          <p className="mb-4 flex items-center gap-2 text-sm text-brand-800">
            <CheckCircle2 className="size-4 text-brand-600" aria-hidden /> {job.source ? `${job.source.wordCount.toLocaleString('en')} words · ~${job.source.pageEstimate} pages · ${job.source.format}` : 'Your paper'}
          </p>
        </PaperPreview>
      </div>
      <aside className="order-1 lg:sticky lg:top-20 lg:order-2 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
        <JobOptions key={`${job.id}-${mode}`} job={job} mode={mode} initial={initial} />
      </aside>
    </div>
  )
}
