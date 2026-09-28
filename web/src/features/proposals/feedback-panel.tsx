import { Download, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { Checkbox, Select, TextArea } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Alert, Badge, Card } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import type { FeedbackComment, FeedbackStatus, Project } from '../../lib/proposal-types'

const STATUS: Record<FeedbackStatus, { label: string; tone: 'neutral' | 'brand' | 'warning' }> = {
  OPEN: { label: 'To do', tone: 'warning' },
  APPLIED: { label: 'Revised', tone: 'brand' },
  DONE_BY_STUDENT: { label: 'Done by you', tone: 'brand' },
  DECLINED: { label: 'Not changing', tone: 'neutral' },
}

/** Supervisor comments: add them, place each on the sections it concerns, then revise those
 * sections from the chapter's tab. The response report lists what was done about each. */
export function FeedbackPanel({ project, onChanged }: { project: Project; onChanged: (p: Project) => void }) {
  const data = useData()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (action: () => Promise<Project | void>) => {
    setBusy(true)
    setError(null)
    try {
      const updated = await action()
      if (updated) onChanged(updated)
      return true
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const open = project.feedback.filter((c) => c.status === 'OPEN')
  const unplaced = open.filter((c) => !c.chapter || !c.sections.length)
  const hasChapter = project.written.length > 0

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        {!project.feedback.length ? (
          <p className="text-sm text-fg-muted">
            Add your supervisor&rsquo;s comments here. PaperAid places each one on the section it is about; you check that, then revise those sections from
            the chapter&rsquo;s tab. Every other section stays exactly as it is.
          </p>
        ) : (
          <>
            {unplaced.length > 0 && (
              <Alert tone="info">
                {unplaced.length === 1 ? 'One comment is' : `${unplaced.length} comments are`} not placed on a section yet. Choose where each applies, or mark
                it done if you handled it yourself.
              </Alert>
            )}
            {project.feedback.map((c, i) => (
              <CommentCard key={c.id} n={i + 1} comment={c} project={project} busy={busy} run={run} />
            ))}
          </>
        )}
      </div>
      <aside className="space-y-4">
        <Card className="space-y-3 p-4">
          <p className="text-sm font-semibold">Add comments</p>
          <TextArea
            label="Paste your supervisor's comments"
            rows={6}
            maxLength={30000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            hint="One comment per line, numbered item or paragraph."
          />
          <Button
            variant="secondary"
            loading={busy}
            disabled={text.trim().length < 3}
            onClick={async () => {
              if (await run(() => data.projects.addFeedback(project.id, text))) setText('')
            }}
          >
            Add these comments
          </Button>
          <FileDropzone
            compact
            label="Or upload the marked-up file"
            hint="Word comments or PDF notes are read with where they sit"
            accept=".docx,.pdf"
            disabled={busy}
            onFile={(file) => run(() => data.projects.addFeedbackFile(project.id, file))}
          />
          {!hasChapter && <p className="text-xs text-fg-subtle">Comments can be placed on sections once a chapter is written.</p>}
        </Card>
        {project.feedback.length > 0 && (
          <Card className="space-y-2 p-4">
            <p className="text-sm font-semibold">Response to your supervisor</p>
            <p className="text-sm text-fg-muted">
              A Word table of every comment, where it applied and what was done{open.length ? `; ${open.length} still to do` : ''}.
            </p>
            <Button variant="secondary" loading={busy} onClick={() => run(() => data.projects.downloadResponse(project.id))}>
              <Download className="size-4" aria-hidden /> Response report
            </Button>
          </Card>
        )}
      </aside>
    </div>
  )
}

function CommentCard({
  n,
  comment,
  project,
  busy,
  run,
}: {
  n: number
  comment: FeedbackComment
  project: Project
  busy: boolean
  run: (action: () => Promise<Project | void>) => Promise<boolean>
}) {
  const data = useData()
  const [response, setResponse] = useState(comment.response)
  const sections = project.written.filter((s) => s.chapter === comment.chapter)
  const chapters = [...new Set(project.written.map((s) => s.chapter))]
  const save = (edit: Partial<{ chapter: number | null; sections: string[]; status: FeedbackStatus; response: string }>) =>
    run(() =>
      data.projects.editFeedback(project.id, comment.id, {
        chapter: comment.chapter,
        sections: comment.sections,
        status: comment.status,
        response: comment.response,
        ...edit,
      }),
    )
  const status = STATUS[comment.status]
  const editable = comment.status === 'OPEN'

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-fg-subtle">{comment.by === 'STUDENT' ? 'Your request' : `Comment ${n}`}</span>
        <Badge tone={status.tone}>
          {status.label}
          {comment.appliedIn ? ` in version ${comment.appliedIn}` : ''}
        </Badge>
        {comment.anchor && <span className="truncate text-xs text-fg-subtle">at &ldquo;{comment.anchor}&rdquo;</span>}
        <Button size="sm" variant="ghost" className="ml-auto" aria-label="Remove comment" disabled={busy} onClick={() => run(() => data.projects.deleteFeedback(project.id, comment.id))}>
          <Trash2 className="size-4" aria-hidden />
        </Button>
      </div>
      <p className="mt-2 text-sm">{comment.text}</p>
      {editable && chapters.length > 0 && (
        <div className="mt-3 space-y-2">
          <Select
            label="Applies to"
            className="max-w-xs"
            value={comment.chapter ?? ''}
            disabled={busy}
            onChange={(e) => save({ chapter: e.target.value ? Number(e.target.value) : null, sections: [] })}
          >
            <option value="">Not placed</option>
            {chapters.map((c) => (
              <option key={c} value={c}>
                Chapter {c}
              </option>
            ))}
          </Select>
          {comment.chapter && (
            <div className="grid gap-1 sm:grid-cols-2">
              {sections.map((s) => (
                <Checkbox
                  key={s.key}
                  disabled={busy}
                  checked={comment.sections.includes(s.key)}
                  onChange={(e) => save({ sections: e.target.checked ? [...comment.sections, s.key] : comment.sections.filter((k) => k !== s.key) })}
                  label={`${s.number} ${s.heading}`}
                />
              ))}
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <TextArea className="min-w-64 flex-1" label="Your reply for the report (optional)" rows={1} maxLength={1000} value={response} onChange={(e) => setResponse(e.target.value)} />
        {response !== comment.response && (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => save({ response })}>
            Save reply
          </Button>
        )}
      </div>
      {comment.status !== 'APPLIED' && (
        <div className="mt-3 flex flex-wrap gap-2">
          {editable ? (
            <>
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => save({ status: 'DONE_BY_STUDENT', response })}>
                I handled it myself
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => save({ status: 'DECLINED', response })}>
                Not changing this
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => save({ status: 'OPEN' })}>
              Reopen
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}
