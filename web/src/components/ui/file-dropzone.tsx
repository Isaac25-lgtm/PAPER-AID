import { clsx } from 'clsx'
import { FileText, UploadCloud, X } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'
import { formatBytes } from '../../lib/format'

interface FileDropzoneProps {
  label: string
  hint: string
  accept: string
  onFile: (file: File) => void
  compact?: boolean
  disabled?: boolean
}

export function FileDropzone({ label, hint, accept, onFile, compact, disabled }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const id = useId()

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && !disabled) onFile(file)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={clsx(
        'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed text-center transition-colors',
        compact ? 'px-4 py-5' : 'px-6 py-10 sm:py-12',
        dragging ? 'border-brand-500 bg-brand-50' : 'border-line-strong bg-surface-subtle hover:border-brand-300',
        disabled && 'opacity-60',
      )}
    >
      <div className={clsx('grid place-items-center rounded-full bg-white text-brand-700 shadow-card ring-1 ring-line', compact ? 'mb-2 size-9' : 'mb-4 size-12')}>
        <UploadCloud className={compact ? 'size-4' : 'size-5'} aria-hidden />
      </div>
      <label htmlFor={id} className="cursor-pointer text-sm font-semibold text-fg">
        <span className="text-brand-700 underline decoration-brand-300 underline-offset-4">{label}</span>
        <span className="hidden font-normal text-fg-muted sm:inline"> or drag it here</span>
      </label>
      <p className="mt-1 text-xs text-fg-subtle">{hint}</p>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = ''
        }}
      />
    </div>
  )
}

export function FileChip({ name, meta, progress, onRemove }: { name: string; meta?: string; progress?: number; onRemove?: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-white p-3 shadow-card">
      <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
        <FileText className="size-5" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{name}</p>
        {progress !== undefined && progress < 100 ? (
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-muted" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label={`Uploading ${name}`}>
            <div className="h-full rounded-full bg-brand-500 transition-[width]" style={{ width: `${progress}%` }} />
          </div>
        ) : (
          meta && <p className="mt-0.5 truncate text-xs text-fg-subtle">{meta}</p>
        )}
      </div>
      {onRemove && (
        <button type="button" onClick={onRemove} className="rounded-md p-1.5 text-fg-subtle hover:bg-surface-muted hover:text-fg" aria-label={`Remove ${name}`}>
          <X className="size-4" />
        </button>
      )}
    </div>
  )
}

export const fileMetaLine = (m: { format: string; sizeBytes: number; wordCount: number; pageEstimate: number }) =>
  `${m.format} · ${formatBytes(m.sizeBytes)} · ${m.wordCount.toLocaleString('en')} words · ~${m.pageEstimate} pages`
