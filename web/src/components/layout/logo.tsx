import { clsx } from 'clsx'
import { Link } from 'react-router'

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={clsx('shrink-0', className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--color-brand-700)" />
      <path d="M10 6.5h8.6l5.4 5.4v13.1a1.5 1.5 0 0 1-1.5 1.5H10A1.5 1.5 0 0 1 8.5 25V8A1.5 1.5 0 0 1 10 6.5Z" fill="#fff" />
      <path d="M18.6 6.5v4a1.4 1.4 0 0 0 1.4 1.4h4Z" fill="var(--color-brand-200)" />
      <path d="m12 19.2 2.8 2.8 5.4-5.8" fill="none" stroke="var(--color-brand-700)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Logo({ to = '/', className }: { to?: string; className?: string }) {
  return (
    <Link to={to} className={clsx('flex items-center gap-2.5 rounded-md', className)} aria-label="PaperAid home">
      <LogoMark className="size-8" />
      <span className="text-[1.3rem] font-bold tracking-tight text-fg">
        Paper<span className="text-brand-600">Aid</span>
      </span>
    </Link>
  )
}
