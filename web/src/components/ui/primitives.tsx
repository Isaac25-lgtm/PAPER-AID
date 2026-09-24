import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx('rounded-xl border border-line bg-surface shadow-card', className)} {...props} />
}

export type Tone = 'neutral' | 'brand' | 'info' | 'warning' | 'danger' | 'violet'

const badgeTones: Record<Tone, string> = {
  neutral: 'bg-surface-muted text-fg-muted ring-line-strong/60',
  brand: 'bg-brand-50 text-brand-800 ring-brand-200',
  info: 'bg-sky-50 text-sky-800 ring-sky-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  danger: 'bg-red-50 text-red-700 ring-red-200',
  violet: 'bg-violet-50 text-violet-800 ring-violet-200',
}

export function Badge({ tone = 'neutral', className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset',
        badgeTones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

const alertStyles = {
  info: { box: 'bg-sky-50 border-sky-200 text-sky-900', icon: Info, iconClass: 'text-sky-600' },
  success: { box: 'bg-brand-50 border-brand-200 text-brand-900', icon: CheckCircle2, iconClass: 'text-brand-600' },
  warning: { box: 'bg-amber-50 border-amber-200 text-amber-950', icon: AlertTriangle, iconClass: 'text-amber-600' },
  danger: { box: 'bg-red-50 border-red-200 text-red-900', icon: XCircle, iconClass: 'text-red-600' },
}

export function Alert({
  tone = 'info',
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof alertStyles
  title?: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const style = alertStyles[tone]
  const Icon = style.icon
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={clsx('flex gap-3 rounded-lg border p-4 text-sm', style.box, className)}>
      <Icon className={clsx('mt-0.5 size-5 shrink-0', style.iconClass)} aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="leading-relaxed opacity-90">{children}</div>}
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx('animate-pulse rounded-md bg-surface-muted', className)} />
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line-strong bg-surface-subtle px-6 py-12 text-center">
      <div className="mb-4 grid size-12 place-items-center rounded-full bg-brand-100 text-brand-700">{icon}</div>
      <h3 className="text-base font-semibold">{title}</h3>
      <div className="mt-1 max-w-sm text-sm text-fg-muted">{children}</div>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={clsx('inline-flex rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold tracking-wide text-brand-700 uppercase ring-1 ring-brand-100', className)}>
      {children}
    </span>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  )
}
