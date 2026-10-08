import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, ChevronDown, Download, FileText, Loader2, Paperclip, Sparkles, X } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Select, TextArea } from '../../components/ui/field'
import { Alert } from '../../components/ui/primitives'
import type { DocFigureData } from '../../lib/work-types'

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
        <h1 className="mt-1 text-xl leading-snug font-medium tracking-tight text-fg sm:text-2xl">{title}</h1>
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
      className="mx-auto w-full max-w-[48rem] bg-white px-1 py-4 text-[16px] leading-[1.8] text-[#111] sm:px-4"
      style={{ fontFamily: "'Times New Roman', Times, 'Liberation Serif', serif" }}
    >
      {children}
    </article>
  )
}

const LINE_COLOURS = ['#1f3a8a', '#c2410c', '#15803d', '#7c3aed', '#0e7490', '#b45309']

/** A graph PaperAid drew from the writer's data (the Word file has the same figure, drawn by the server). */
export function DocFigure({ figure }: { figure: DocFigureData }) {
  const points = figure.series.flatMap((s) => s.points)
  if (points.length < 2) return null
  const [w, h, left, bottom, top, right] = [560, 320, 56, 44, 16, 16]
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const [y0, y1] = [Math.min(0, ...ys), Math.max(...ys)]
  const sx = (x: number) => left + ((x - x0) / (x1 - x0 || 1)) * (w - left - right)
  const sy = (y: number) => h - bottom - ((y - y0) / (y1 - y0 || 1)) * (h - top - bottom)
  const ticks = (a: number, b: number) => [0, 0.25, 0.5, 0.75, 1].map((t) => a + t * (b - a))
  const fmt = (v: number) => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : Number(v.toPrecision(3)).toString())
  return (
    <figure className="my-5">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-xl" role="img" aria-label={figure.caption}>
        <line x1={left} y1={h - bottom} x2={w - right} y2={h - bottom} stroke="#9ca3af" />
        <line x1={left} y1={top} x2={left} y2={h - bottom} stroke="#9ca3af" />
        {ticks(x0, x1).map((v) => (
          <text key={`x${v}`} x={sx(v)} y={h - bottom + 16} fontSize="11" textAnchor="middle" fill="#374151">{fmt(v)}</text>
        ))}
        {ticks(y0, y1).map((v) => (
          <text key={`y${v}`} x={left - 6} y={sy(v) + 4} fontSize="11" textAnchor="end" fill="#374151">{fmt(v)}</text>
        ))}
        <text x={(left + w - right) / 2} y={h - 6} fontSize="12" textAnchor="middle" fill="#111827">{figure.xAxis}</text>
        <text x={14} y={(top + h - bottom) / 2} fontSize="12" textAnchor="middle" fill="#111827" transform={`rotate(-90 14 ${(top + h - bottom) / 2})`}>{figure.yAxis}</text>
        {figure.series.map((s, i) => {
          const sorted = [...s.points].sort((a, b) => a.x - b.x)
          return (
            <g key={s.label}>
              <polyline fill="none" stroke={LINE_COLOURS[i % LINE_COLOURS.length]} strokeWidth="2" points={sorted.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')} />
              {figure.series.length > 1 && (
                <text x={w - right} y={top + 14 * (i + 1)} fontSize="11" textAnchor="end" fill={LINE_COLOURS[i % LINE_COLOURS.length]}>{s.label}</text>
              )}
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-1 text-sm italic">{figure.caption}</figcaption>
    </figure>
  )
}

export function DocTable({ caption, rows }: { caption: string; rows: string[][] }) {
  if (rows.length < 2) return null
  return (
    <figure className="my-5 overflow-x-auto">
      <figcaption className="mb-1.5 text-sm font-semibold">{caption}</figcaption>
      <table className="w-full border-collapse text-[13px] leading-snug">
        <thead>
          <tr>
            {rows[0].map((c, i) => (
              <th key={i} className="border border-[#999] bg-[#f3f4f6] px-2 py-1.5 text-left font-semibold">
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

/** A numbered sub-heading line placed by the server ("1.4.1 General Objective"). */
export const SUBHEADING = /^\d{1,2}(?:\.\d{1,2}){1,2} [A-Z][A-Za-z ]{2,60}$/

/** A paragraph, with any marked gap ("[target to be added]") highlighted for the student. */
export function Para({ text, changed }: { text: string; changed?: boolean }) {
  if (SUBHEADING.test(text.trim())) return <h3 className="mt-4 text-[15px] font-semibold">{text}</h3>
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
export function ChangeBox({ parts, busy, running, onApply, whole = 'The whole document', runningText = 'Applying your changes… this usually takes a few minutes. The new version opens here.' }: {
  parts: { key: string; label: string }[]; busy: boolean; running: boolean; onApply: (text: string, part: string, file: File | null) => Promise<boolean>; whole?: string
  /** What is running, when it is not a change to this document (another chapter being written). */
  runningText?: string
}) {
  const [text, setText] = useState('')
  const [part, setPart] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const pick = useId()
  if (running)
    return (
      <p className="flex items-center gap-2 rounded-lg bg-brand-50 p-3 text-sm font-medium text-brand-900" role="status">
        <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden /> {runningText}
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
