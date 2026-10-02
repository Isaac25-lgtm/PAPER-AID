import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, ChevronDown, Download, FileText, Loader2, Paperclip, Sparkles, X } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Select, TextArea } from '../../components/ui/field'
import { Alert } from '../../components/ui/primitives'

/** The workspace (owner decision 2026-10-01): the document on the left as it reads on paper, and on
 *  the right what the student can do with it: what still needs them, asking for changes (with a
 *  document for context), earlier versions. Downloads stay in the header, always in reach. */

export type StatusTone = 'ready' | 'warn' | 'input' | 'danger' | 'running' | 'idle'

export interface WorkspaceStatus {
  label: string
  tone: StatusTone
}

const TONES: Record<StatusTone, string> = {
  ready: 'bg-brand-50 text-brand-800 ring-brand-200',
  warn: 'bg-amber-50 text-amber-900 ring-amber-200',
  input: 'bg-amber-50 text-amber-900 ring-amber-300',
  danger: 'bg-red-50 text-red-800 ring-red-200',
  running: 'bg-brand-50 text-brand-800 ring-brand-200',
  idle: 'bg-surface-muted text-fg-muted ring-line',
}

export function StatusChip({ status }: { status: WorkspaceStatus }) {
  const Icon = status.tone === 'ready' ? CheckCircle2 : status.tone === 'running' ? Loader2 : status.tone === 'idle' ? FileText : AlertTriangle
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap ring-1', TONES[status.tone])} role="status">
      <Icon className={clsx('size-3.5', status.tone === 'running' && 'animate-spin')} aria-hidden /> {status.label}
    </span>
  )
}

export function WorkspaceHeader({ title, meta, status, onWord, onPdf, extra }: {
  title: string; meta: string; status: WorkspaceStatus | null; onWord: () => Promise<void>; onPdf: () => Promise<void>; extra?: ReactNode
}) {
  const [busy, setBusy] = useState<'word' | 'pdf' | null>(null)
  const run = async (which: 'word' | 'pdf', action: () => Promise<void>) => {
    setBusy(which)
    try {
      await action()
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <Link to="/app/work" className="text-sm font-medium text-fg-muted hover:text-fg">
          ← Your work
        </Link>
        <h1 className="mt-1 text-xl leading-snug font-bold tracking-tight text-fg sm:text-2xl">{title}</h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
          <span>{meta}</span>
          {status && <StatusChip status={status} />}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {extra}
        <Button loading={busy === 'word'} onClick={() => run('word', onWord)}>
          <Download className="size-4" aria-hidden /> Download Word
        </Button>
        <Button variant="secondary" loading={busy === 'pdf'} onClick={() => run('pdf', onPdf)}>
          <FileText className="size-4" aria-hidden /> PDF
        </Button>
      </div>
    </div>
  )
}

/** The page: a sheet in the document's own typeface, so the preview reads like the download. */
export function Paper({ children }: { children: ReactNode }) {
  return (
    <article
      className="mx-auto w-full max-w-[52rem] rounded-sm bg-white px-6 py-10 text-[15px] leading-[1.75] text-[#111] shadow-raised ring-1 ring-line sm:px-14 sm:py-14"
      style={{ fontFamily: "'Times New Roman', Times, 'Liberation Serif', serif" }}
    >
      {children}
    </article>
  )
}

export function DocTable({ caption, rows }: { caption: string; rows: string[][] }) {
  if (rows.length < 2) return null
  return (
    <figure className="my-5 overflow-x-auto">
      <figcaption className="mb-1.5 text-sm font-bold">{caption}</figcaption>
      <table className="w-full border-collapse text-[13px] leading-snug">
        <thead>
          <tr>
            {rows[0].map((c, i) => (
              <th key={i} className="border border-[#999] bg-[#eef5f0] px-2 py-1.5 text-left font-bold">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((row, r) => (
            <tr key={r}>
              {row.map((c, i) => (
                <td key={i} className={clsx('border border-[#999] px-2 py-1.5 align-top', c.includes('to be added') && 'bg-amber-50 font-semibold text-amber-900')}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

/** A paragraph, with any marked gap ("[target to be added]") highlighted for the student. */
export function Para({ text, changed }: { text: string; changed?: boolean }) {
  const parts = text.split(/(\[[^\]]*to be added\])/)
  return (
    <p className={clsx('mt-3 text-justify', changed && '-mx-2 rounded bg-brand-50 px-2')}>
      {parts.map((part, i) =>
        /to be added\]$/.test(part) ? (
          <mark key={i} className="rounded bg-amber-100 px-1 font-semibold text-amber-900">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </p>
  )
}

/** A panel section on the right, folded open or closed. */
export function PanelSection({ title, badge, defaultOpen = true, children }: { title: string; badge?: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <section className="rounded-2xl border border-line bg-white shadow-card">
      <button className="flex w-full items-center gap-2 px-5 py-4 text-left" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <span className="flex-1 text-base font-semibold text-fg">{title}</span>
        {badge}
        <ChevronDown className={clsx('size-4 text-fg-subtle transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div id={id} className="border-t border-line px-5 pt-4 pb-5">
          {children}
        </div>
      )}
    </section>
  )
}

export interface CheckLine {
  id: string
  ok: boolean
  text: string
  note?: string
  action?: string
  yours?: boolean
}

/** What PaperAid checked, in plain words: what passes, then what needs a look. Never a mark. */
export function ChecksList({ lines }: { lines: CheckLine[] }) {
  const open = lines.filter((l) => !l.ok)
  const passed = lines.filter((l) => l.ok)
  return (
    <div className="space-y-2">
      {open.map((l) => (
        <div key={l.id} className="flex gap-2.5 rounded-lg bg-amber-50 p-2.5 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden />
          <div>
            <p className="font-medium text-amber-950">
              {l.text}
              {l.yours && <span className="ml-1.5 text-xs font-semibold text-amber-800">(only you can add this)</span>}
            </p>
            {l.note && <p className="mt-0.5 text-xs text-amber-900">{l.note}</p>}
            {l.action && <p className="mt-0.5 text-xs font-medium text-amber-950">Next: {l.action}</p>}
          </div>
        </div>
      ))}
      {passed.slice(0, 6).map((l) => (
        <p key={l.id} className="flex items-start gap-2.5 text-sm text-fg">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-700" aria-hidden /> {l.text}
        </p>
      ))}
      {passed.length > 6 && <p className="pl-6 text-xs text-fg-subtle">and {passed.length - 6} more checks passed.</p>}
      <p className="pt-1 text-xs text-fg-subtle">PaperAid’s checks against your requirements: a guide, not a mark.</p>
    </div>
  )
}

/** Ask for changes: the student's own words, which part, and an optional document for context. */
export function ChangeBox({ parts, busy, running, onApply, whole = 'The whole document' }: {
  parts: { key: string; label: string }[]; busy: boolean; running: boolean; onApply: (text: string, part: string, file: File | null) => Promise<boolean>; whole?: string
}) {
  const [text, setText] = useState('')
  const [part, setPart] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const pick = useId()
  if (running)
    return (
      <p className="flex items-center gap-2 rounded-lg bg-brand-50 p-3 text-sm font-medium text-brand-900" role="status">
        <Loader2 className="size-4 animate-spin" aria-hidden /> Applying your changes… this usually takes a few minutes. The new version opens here.
      </p>
    )
  return (
    <div className="space-y-3">
      <TextArea
        label="Tell us what to change, in your own words"
        rows={3}
        maxLength={2000}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. Make the conclusion stronger, or add a Ugandan example in section 2"
      />
      <Select label="Which part?" value={part} onChange={(e) => setPart(e.target.value)}>
        <option value="">{whole}</option>
        {parts.map((p) => (
          <option key={p.key} value={p.key}>
            {p.label}
          </option>
        ))}
      </Select>
      <div>
        <label htmlFor={pick} className="flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-line-strong px-3 py-2.5 text-sm text-fg-muted hover:border-brand-300">
          <Paperclip className="size-4" aria-hidden />
          {file ? <span className="min-w-0 flex-1 truncate font-medium text-fg">{file.name}</span> : <span className="flex-1">Add a document for more context (optional): Word or PDF. PaperAid uses its first 1,000 words.</span>}
          {file && (
            <button className="rounded p-0.5 hover:text-red-600" aria-label="Remove the document" onClick={(e) => { e.preventDefault(); setFile(null) }}>
              <X className="size-4" aria-hidden />
            </button>
          )}
        </label>
        <input id={pick} type="file" accept=".docx,.pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      <Button
        className="w-full"
        loading={busy}
        disabled={text.trim().length < 3}
        onClick={async () => {
          if (await onApply(text.trim(), part, file)) {
            setText('')
            setPart('')
            setFile(null)
          }
        }}
      >
        <Sparkles className="size-4" aria-hidden /> Apply changes
      </Button>
    </div>
  )
}

export function Versions({ versions, current, onPick }: { versions: { version: number; createdAt: string; words: number; note: string }[]; current: number; onPick: (v: number) => void }) {
  return (
    <ul className="space-y-1.5">
      {[...versions].reverse().map((v) => (
        <li key={v.version}>
          <button
            onClick={() => onPick(v.version)}
            className={clsx('flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm', v.version === current ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-surface-muted')}
            aria-current={v.version === current ? 'true' : undefined}
          >
            <FileText className="size-4 text-fg-subtle" aria-hidden />
            <span className="font-medium text-fg">Version {v.version}</span>
            {v.version === current && <span className="rounded bg-brand-100 px-1.5 text-[11px] font-semibold text-brand-800">Shown</span>}
            <span className="ml-auto text-xs text-fg-subtle">
              {v.words.toLocaleString()} words · {new Date(v.createdAt).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </span>
          </button>
          {v.note && <p className="pl-9 text-xs text-fg-subtle">{v.note}</p>}
        </li>
      ))}
    </ul>
  )
}

export function ErrorNote({ text }: { text: string | null }) {
  return text ? <Alert tone="warning">{text}</Alert> : null
}
