import { clsx } from 'clsx'
import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle' | 'inverse'
type Size = 'sm' | 'md' | 'lg'

// Calm buttons (redesign 2026-10-04): one solid accent, white secondary with a hairline, small corners.
const variants: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15),0_1px_2px_rgb(16_24_40/0.08)] hover:bg-brand-700 active:bg-brand-800',
  secondary: 'bg-white text-fg border border-line shadow-[0_1px_2px_rgb(16_24_40/0.04)] hover:bg-surface-subtle hover:border-line-strong',
  subtle: 'bg-brand-50 text-brand-700 hover:bg-brand-100',
  ghost: 'text-fg-muted hover:bg-surface-muted hover:text-fg',
  danger: 'bg-red-600 text-white hover:bg-red-700',
  inverse: 'bg-white text-brand-700 hover:bg-brand-50',
}

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-lg',
  md: 'h-9 px-4 text-sm gap-2 rounded-lg',
  lg: 'h-12 px-6 text-base gap-2.5 rounded-xl',
}

export function buttonClass(variant: Variant = 'primary', size: Size = 'md', className?: string) {
  return clsx(
    'inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors duration-200 select-none',
    'disabled:pointer-events-none disabled:opacity-50',
    variants[variant],
    sizes[size],
    className,
  )
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

export function Button({ variant, size, loading, className, children, disabled, type = 'button', ...props }: ButtonProps) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function ButtonLink({ variant, size, className, ...props }: LinkProps & { variant?: Variant; size?: Size }) {
  return <Link className={buttonClass(variant, size, className)} {...props} />
}
