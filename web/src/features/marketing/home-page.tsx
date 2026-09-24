import { ArrowRight, Ban, BookLock, CreditCard, Download, FileSearch, FileUp, Lock, ShieldCheck, SlidersHorizontal, Trash2 } from 'lucide-react'
import { ButtonLink } from '../../components/ui/button'
import { Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { HeroPreview } from './hero-preview'
import { FinalCta, PricingCards, ServiceGrid } from './sections'

export function HomePage() {
  useTitle('')
  const { config } = useData()

  const steps = [
    { icon: FileUp, title: 'Upload your paper', body: 'A Word document or text-based PDF, plus your university guide if you have one.' },
    { icon: SlidersHorizontal, title: 'Choose services', body: 'Check, refine, format — or combine them. You see what each one does before you choose.' },
    config.paymentsEnabled
      ? { icon: CreditCard, title: 'Pay with Mobile Money', body: 'Your price is calculated from the length of your paper. No subscriptions.' }
      : { icon: FileSearch, title: 'Review your quote', body: "You'll see the exact price for your paper. During the beta, jobs are free." },
    { icon: Download, title: 'Download', body: 'A Word file you can review, plus a report of every change and why it was made.' },
  ]

  return (
    <>
      <section className="relative overflow-hidden">
        <div aria-hidden className="absolute inset-x-0 top-0 -z-10 h-[40rem] bg-gradient-to-b from-brand-50/80 to-white" />
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-12 pb-16 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:gap-14 lg:pt-20 lg:pb-24">
          <div>
            <Eyebrow>For university students</Eyebrow>
            <h1 className="mt-5 text-[2.5rem] leading-[1.08] font-extrabold sm:text-5xl lg:text-[3.15rem]">
              Submit a paper that&rsquo;s <span className="text-brand-600">clear, correct</span> and properly formatted.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-fg-muted">
              Upload your draft. PaperAid points out weak and formulaic passages, refines them without touching your citations, and applies academic
              formatting — then gives you back a Word file you can review.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <ButtonLink to="/app/new" size="lg">
                <FileUp className="size-5" aria-hidden /> Upload your paper
              </ButtonLink>
              <ButtonLink to="/#how-it-works" size="lg" variant="secondary">
                See how it works
              </ButtonLink>
            </div>
            <ul className="mt-8 grid gap-x-6 gap-y-2.5 text-sm text-fg-muted sm:flex sm:flex-wrap">
              <li className="flex items-center gap-2">
                <Lock className="size-4 text-brand-600" aria-hidden /> Citations and data stay intact
              </li>
              <li className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-brand-600" aria-hidden /> Private, deleted after {config.retentionDays} days
              </li>
              {!config.paymentsEnabled && (
                <li className="flex items-center gap-2">
                  <BookLock className="size-4 text-brand-600" aria-hidden /> Free during beta
                </li>
              )}
            </ul>
          </div>
          <HeroPreview />
        </div>
      </section>

      <section className="border-y border-line bg-surface-subtle py-16 sm:py-20" aria-labelledby="features-title">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <Eyebrow>What PaperAid does</Eyebrow>
              <h2 id="features-title" className="mt-4 text-3xl font-bold sm:text-4xl">
                One upload. The work your paper needs.
              </h2>
            </div>
            <ButtonLink to="/features" variant="ghost" className="self-start sm:self-auto">
              Service details <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
          </div>
          <div className="mt-10">
            <ServiceGrid />
          </div>
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-20 py-16 sm:py-20" aria-labelledby="how-title">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="max-w-2xl">
            <Eyebrow>How it works</Eyebrow>
            <h2 id="how-title" className="mt-4 text-3xl font-bold sm:text-4xl">
              From draft to a better paper in four steps.
            </h2>
            <p className="mt-3 text-fg-muted">No prompts, no chat. Hand over your paper, choose the work, and come back to a finished result.</p>
          </div>
          <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step, i) => (
              <li key={step.title} className="relative rounded-2xl border border-line bg-white p-6 shadow-card">
                <div className="flex items-center gap-3">
                  <span className="grid size-8 place-items-center rounded-full bg-brand-700 text-sm font-bold text-white">{i + 1}</span>
                  <step.icon className="size-5 text-brand-600" aria-hidden />
                </div>
                <h3 className="mt-5 font-semibold">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="bg-brand-950 py-16 text-white sm:py-20" aria-labelledby="trust-title">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="inline-flex rounded-full bg-white/10 px-3 py-1 text-xs font-semibold tracking-wide text-brand-200 uppercase">Built to protect your work</span>
            <h2 id="trust-title" className="mt-4 text-3xl font-bold text-white sm:text-4xl">
              Your ideas stay yours.
            </h2>
            <p className="mt-4 leading-relaxed text-brand-100/90">
              PaperAid improves how your paper reads and looks. It does not invent sources, change your findings or write your argument for you — and
              every change is shown to you before you submit anything.
            </p>
            <p className="mt-6 rounded-xl bg-white/5 p-4 text-sm leading-relaxed text-brand-100/80 ring-1 ring-white/10">
              Our AI-likeness check is an estimate of writing patterns. No detector — ours or anyone else&rsquo;s — can prove who wrote a text, and we
              never promise a result on another service.
            </p>
          </div>
          <ul className="grid gap-4 sm:grid-cols-2">
            {[
              { icon: Lock, title: 'Citations locked', body: 'Citations, quotes, numbers and links are protected during editing and checked afterwards.' },
              { icon: ShieldCheck, title: 'Formatting never rewrites', body: 'Formatting jobs are automatically checked to confirm not a single word changed.' },
              { icon: Ban, title: 'Nothing invented', body: 'An independent accuracy check rejects changes that add claims, sources or data.' },
              { icon: Trash2, title: `Deleted after ${config.retentionDays} days`, body: 'Your files are private to your account and removed automatically. Delete them sooner any time.' },
            ].map((item) => (
              <li key={item.title} className="rounded-2xl bg-white/5 p-5 ring-1 ring-white/10">
                <item.icon className="size-5 text-brand-300" aria-hidden />
                <h3 className="mt-3 font-semibold text-white">{item.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-brand-100/80">{item.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="py-16 sm:py-20" aria-labelledby="pricing-title">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-[18rem_1fr]">
            <div>
              <Eyebrow>Simple pricing</Eyebrow>
              <h2 id="pricing-title" className="mt-4 text-3xl font-bold">
                Pay for the paper, not a subscription.
              </h2>
              <p className="mt-3 text-fg-muted">
                Your exact price is calculated after upload, from your paper&rsquo;s length and the services you choose.
                {!config.paymentsEnabled && ' During the beta, every job is free.'}
              </p>
              <ButtonLink to="/pricing" variant="ghost" className="mt-4 -ml-4">
                How pricing works <ArrowRight className="size-4" aria-hidden />
              </ButtonLink>
            </div>
            <PricingCards />
          </div>
        </div>
      </section>

      <FinalCta />
    </>
  )
}
