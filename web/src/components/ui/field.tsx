import { clsx } from 'clsx'
import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'

const control =
  'w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-fg shadow-sm transition-colors placeholder:text-fg-subtle hover:border-brand-300 focus:border-brand-500 focus:outline-none focus:ring-3 focus:ring-brand-100 disabled:bg-surface-muted aria-invalid:border-red-400 aria-invalid:focus:ring-red-100'

interface FieldProps {
  label: string
  hint?: ReactNode
  error?: string | null
}

export function Input({ label, hint, error, className, ...props }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-fg">
        {label}
      </label>
      <input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy} className={clsx(control, 'h-11')} {...props} />
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-fg-subtle">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1.5 text-xs font-medium text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

export function Select({ label, hint, className, children, ...props }: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-fg">
        {label}
      </label>
      <select id={id} className={clsx(control, 'h-10 pr-8')} aria-describedby={hint ? `${id}-hint` : undefined} {...props}>
        {children}
      </select>
      {hint && (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-fg-subtle">
          {hint}
        </p>
      )}
    </div>
  )
}

export function Checkbox({ label, className, ...props }: { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <div className={clsx('flex gap-3', className)}>
      <input id={id} type="checkbox" className="mt-0.5 size-4 shrink-0 rounded border-line-strong accent-brand-700" {...props} />
      <label htmlFor={id} className="text-sm leading-snug text-fg-muted">
        {label}
      </label>
    </div>
  )
}
