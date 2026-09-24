import { clsx } from 'clsx'
import { ArrowRight, Check } from 'lucide-react'
import { Link } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Badge } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { formatUGX } from '../../lib/format'
import { AVAILABILITY_BADGE, SERVICES, SERVICE_ORDER } from '../../lib/services'
import type { ServiceId } from '../../lib/types'

export function ServiceGrid() {
  const { config } = useData()
  return (
    <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
      {SERVICE_ORDER.map((id) => {
        const s = SERVICES[id]
        const availability = config.availability[id]
        const soon = availability !== 'available'
        return (
          <li
            key={id}
            className={clsx(
              'relative flex gap-4 rounded-2xl border border-line bg-white p-5 transition-shadow sm:block sm:p-6',
              !soon && 'shadow-card hover:shadow-raised',
            )}
          >
            <div className={clsx('grid size-11 shrink-0 place-items-center rounded-xl', soon ? 'bg-surface-muted text-fg-subtle' : 'bg-brand-50 text-brand-700')}>
              <s.icon className="size-5" aria-hidden />
            </div>
            {availability !== 'available' && <Badge className="absolute top-4 right-4 sm:top-6 sm:right-6">{AVAILABILITY_BADGE[availability]}</Badge>}
            <div className="min-w-0">
              <h3 className={clsx('text-base font-semibold sm:mt-5', soon && 'text-fg-muted')}>{s.name}</h3>
              <p className="mt-1 text-sm leading-relaxed text-fg-muted sm:mt-1.5">{s.short}</p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

const PRICED: { id: ServiceId; blurb: string; popular?: boolean }[] = [
  { id: 'AI_CHECK', blurb: 'Writing-pattern report with passage-level feedback.' },
  { id: 'REFINE', blurb: 'AI Check, then refinement of flagged passages with an accuracy audit.', popular: true },
  { id: 'FORMAT', blurb: 'APA or Harvard layout, headings, spacing and page numbers.' },
]

export function PricingCards() {
  const { config } = useData()
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {PRICED.map(({ id, blurb, popular }) => (
        <div
          key={id}
          className={clsx('relative flex flex-col rounded-2xl border bg-white p-6', popular ? 'border-brand-500 shadow-raised ring-1 ring-brand-500' : 'border-line shadow-card')}
        >
          {popular && <span className="absolute -top-3 left-6 rounded-full bg-brand-700 px-3 py-1 text-xs font-semibold text-white">Most popular</span>}
          <h3 className="text-base font-semibold">{SERVICES[id].name}</h3>
          <p className="mt-3 text-sm text-fg-subtle">from</p>
          <p className="text-3xl font-bold tracking-tight text-brand-800">{formatUGX(config.indicativeFrom[id])}</p>
          <p className="mt-3 flex-1 text-sm text-fg-muted">{blurb}</p>
          <ul className="mt-5 space-y-2 border-t border-line pt-5">
            {SERVICES[id].youGet.map((item) => (
              <li key={item} className="flex gap-2 text-sm text-fg-muted">
                <Check className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {item}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export function FinalCta() {
  return (
    <section className="px-4 pb-20 sm:px-6">
      <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl bg-brand-800 px-6 py-14 text-center sm:px-12">
        <div aria-hidden className="absolute -top-24 -right-24 size-72 rounded-full bg-brand-600/40 blur-3xl" />
        <div aria-hidden className="absolute -bottom-24 -left-24 size-72 rounded-full bg-brand-500/30 blur-3xl" />
        <h2 className="relative text-3xl font-bold text-white sm:text-4xl">Ready when your deadline is.</h2>
        <p className="relative mx-auto mt-3 max-w-xl text-brand-100">Upload your draft and see exactly what PaperAid would change — before you commit to anything.</p>
        <div className="relative mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink to="/app/new" size="lg" variant="inverse">
            Upload your paper <ArrowRight className="size-4" aria-hidden />
          </ButtonLink>
          <Link to="/pricing" className="inline-flex h-12 items-center justify-center px-4 text-sm font-semibold text-white underline-offset-4 hover:underline">
            See pricing
          </Link>
        </div>
      </div>
    </section>
  )
}
