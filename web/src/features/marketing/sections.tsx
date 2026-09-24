import { clsx } from 'clsx'
import { ArrowRight, Scale, ScanSearch, Wallet } from 'lucide-react'
import { Link } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Badge } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { AVAILABILITY_BADGE, SERVICES, SERVICE_ORDER } from '../../lib/services'

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

// How PaperAid is paid for. There is no price list: every paper is priced from the work it
// actually needs, so the site explains the model and never shows made-up amounts.
const PRICING_STEPS = [
  {
    icon: Wallet,
    title: 'Top up credits',
    body: 'Add credits from UGX 5,000 with mobile money, with the dollar equivalent shown. Credits never expire.',
  },
  {
    icon: ScanSearch,
    title: 'See your estimate first',
    body: 'After upload, PaperAid sizes the work your paper needs and shows the price before anything runs.',
  },
  {
    icon: Scale,
    title: 'Pay for the work done',
    body: 'You are charged for the work your paper actually needed, never more than your estimate. Unused credit returns to your balance.',
  },
]

export function PricingModel() {
  const { config } = useData()
  return (
    <div>
      <ol className="grid gap-4 md:grid-cols-3">
        {PRICING_STEPS.map((step, i) => (
          <li key={step.title} className={clsx('relative rounded-2xl border bg-white p-6', i === 1 ? 'border-brand-500 shadow-raised ring-1 ring-brand-500' : 'border-line shadow-card')}>
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-brand-50 text-brand-700">
                <step.icon className="size-5" aria-hidden />
              </span>
              <span className="text-xs font-semibold tracking-wide text-fg-subtle uppercase">Step {i + 1}</span>
            </div>
            <h3 className="mt-4 text-base font-semibold">{step.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{step.body}</p>
          </li>
        ))}
      </ol>
      {!config.paymentsEnabled && (
        <p className="mt-4 text-sm text-fg-subtle">Payments aren&rsquo;t live yet. Top-ups open when mobile-money payments launch; until then, beta jobs run without charge.</p>
      )}
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
            How pricing works
          </Link>
        </div>
      </div>
    </section>
  )
}
