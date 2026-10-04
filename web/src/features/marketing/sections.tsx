import { clsx } from 'clsx'
import { ArrowRight } from 'lucide-react'
import { createElement, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Badge } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { AVAILABILITY_BADGE, PUBLIC_SECTIONS } from '../../lib/services'

/** A section that fades and rises gently into view once (redesign 2026-10-04). Reduced motion is honoured
 *  by the global rule that shortens every transition. */
export function Reveal({ as = 'div', className, delay = 0, children }: { as?: 'div' | 'li' | 'ul' | 'section'; className?: string; delay?: number; children: ReactNode }) {
  const ref = useRef<HTMLElement | null>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    // shown once it is in view or already above it: a fast scroll or a jump to an anchor never leaves a section hidden
    const check = () => {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.94) {
        setShown(true)
        window.removeEventListener('scroll', check)
        window.removeEventListener('resize', check)
      }
    }
    check()
    window.addEventListener('scroll', check, { passive: true })
    window.addEventListener('resize', check)
    return () => {
      window.removeEventListener('scroll', check)
      window.removeEventListener('resize', check)
    }
  }, [])
  return createElement(as, {
    ref,
    className: clsx('transition-[opacity,transform] duration-[600ms] ease-[cubic-bezier(0.2,0.8,0.3,1)]', shown ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0', className),
    style: { transitionDelay: `${delay}ms` },
  }, children)
}

export function ServiceGrid() {
  const { config } = useData()
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {PUBLIC_SECTIONS.map((s) => {
        const availability = config.availability[s.service]
        const soon = availability !== 'available'
        return (
          <li key={s.id} className="relative rounded-lg border border-line bg-white p-5 sm:p-6">
            <s.icon className={clsx('size-5', soon ? 'text-fg-subtle' : 'text-brand-600')} aria-hidden />
            {availability !== 'available' && <Badge className="absolute top-5 right-5">{AVAILABILITY_BADGE[availability]}</Badge>}
            <h3 className="mt-4 text-lg font-medium text-fg">{s.name}</h3>
            <p className="mt-1.5 text-[15px] leading-relaxed text-fg-muted">{s.short}</p>
          </li>
        )
      })}
    </ul>
  )
}

// How PaperAid is paid for: fixed prices in credits by paper length (owner decisions 2026-09-28 and 2026-10-01).
const PRICING_STEPS = [
  { title: 'Credits', body: 'You pay with credits, from 10 credits (UGX 10,000). Credits never expire. While PaperAid is in testing, nothing is charged.' },
  { title: 'Fixed prices by length', body: 'Every service has a fixed price in credits for your paper’s length. Credits are reserved when you start and charged only for what is delivered.' },
  { title: 'Pay only for what you get', body: 'If part of a job can’t be delivered, you pay only for the part that was. A job that fails costs nothing.' },
]

export function PricingModel() {
  const { config } = useData()
  return (
    <div>
      <ol className="grid gap-5 md:grid-cols-3">
        {PRICING_STEPS.map((step, i) => (
          <li key={step.title} className="rounded-lg border border-line bg-white p-5">
            <span className="block text-[2.9rem] leading-none font-medium tracking-[-0.04em] text-[#d1d5dc]">{String(i + 1).padStart(2, '0')}</span>
            <h3 className="mt-5 text-xl font-medium tracking-[-0.01em] text-fg">{step.title}</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-fg-subtle">{step.body}</p>
          </li>
        ))}
      </ol>
      {!config.paymentsEnabled && (
        <p className="mt-5 text-sm text-fg-subtle">Payments aren’t live yet. Top-ups open when mobile-money payments launch; until then, beta jobs run without charge.</p>
      )}
    </div>
  )
}

export function FinalCta() {
  return (
    <section className="border-t border-line px-4 py-20 sm:px-6 sm:py-24">
      <Reveal className="mx-auto max-w-2xl text-center">
        <h2 className="text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.6rem]">Make progress on the work that matters, today</h2>
        <p className="mt-4 text-lg text-fg-muted">Tell PaperAid what you need and press Start. Review the result on screen, ask for changes, then download it.</p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <ButtonLink to="/app/new" size="lg">
            Get started <ArrowRight className="size-4" aria-hidden />
          </ButtonLink>
          <Link to="/pricing" className="inline-flex h-12 items-center px-4 text-[15px] font-medium text-fg-muted hover:text-fg">
            How pricing works
          </Link>
        </div>
      </Reveal>
    </section>
  )
}
