import { clsx } from 'clsx'
import { Link } from 'react-router'

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={clsx('shrink-0', className)} aria-hidden>
      {/* PaperAid's mark (2026-10-04): a page, a path forming a P, and a small spark */}
      <path d="M8.5 3h10.2L26 10.3V26a3 3 0 0 1-3 3H8.5a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z" fill="var(--color-brand-600)" />
      <path d="M18.7 3v5.3a2 2 0 0 0 2 2H26Z" fill="var(--color-brand-300)" />
      <path d="M11.2 24.2V13.4h4.6a3.6 3.6 0 0 1 0 7.2h-4.6" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="m21.6 18.6.75 1.6 1.6.75-1.6.75-.75 1.6-.75-1.6-1.6-.75 1.6-.75Z" fill="#fff" />
    </svg>
  )
}

export function Logo({ to = '/', className }: { to?: string; className?: string }) {
  return (
    <Link to={to} className={clsx('flex items-center gap-2.5 rounded-md', className)} aria-label="PaperAid home">
      <LogoMark className="size-8" />
      <span className="text-[1.25rem] font-semibold tracking-tight text-fg">PaperAid</span>
    </Link>
  )
}
