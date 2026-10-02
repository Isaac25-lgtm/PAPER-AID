import { Check, Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge, Card, Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { formatTokenNumber } from '../../lib/format'
import type { ServiceId } from '../../lib/types'
import { AVAILABILITY_BADGE, PUBLIC_SECTIONS } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import { FinalCta, PricingModel } from './sections'

function PageHero({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="border-b border-line bg-gradient-to-b from-brand-50/70 to-white">
      <div className="mx-auto max-w-3xl px-4 py-14 text-center sm:px-6 sm:py-20">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">{title}</h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-fg-muted">{children}</p>
      </div>
    </section>
  )
}

export function FeaturesPage() {
  useTitle('Features')
  const { config } = useData()
  return (
    <>
      <PageHero eyebrow="Features" title="What PaperAid does, and exactly what each service changes.">
        Write coursework, a research proposal or a funding proposal, check and finish your own paper, or format a finished one. You always know what will be changed, what will be left alone and what you
        get back.
      </PageHero>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-14 sm:px-6">
        {PUBLIC_SECTIONS.map((s) => {
          const availability = config.availability[s.service]
          return (
            <Card key={s.id} className="p-6 sm:p-8">
              <div className="flex flex-col gap-6 md:flex-row">
                <div className="md:w-72 md:shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="grid size-11 place-items-center rounded-xl bg-brand-50 text-brand-700">
                      <s.icon className="size-5" aria-hidden />
                    </div>
                    {availability !== 'available' && <Badge>{AVAILABILITY_BADGE[availability]}</Badge>}
                  </div>
                  <h2 className="mt-4 text-xl font-bold">{s.name}</h2>
                  <p className="mt-2 text-sm text-fg-muted">{s.short}</p>
                  <p className="mt-4 text-xs text-fg-subtle">Accepts: {s.accepts}</p>
                </div>
                <div className="grid flex-1 gap-6 sm:grid-cols-2">
                  <div>
                    <h3 className="text-sm font-semibold">You get</h3>
                    <ul className="mt-3 space-y-2">
                      {s.youGet.map((x) => (
                        <li key={x} className="flex gap-2 text-sm text-fg-muted">
                          <Check className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {x}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold">Stays untouched</h3>
                    <ul className="mt-3 space-y-2">
                      {s.untouched.map((x) => (
                        <li key={x} className="flex gap-2 text-sm text-fg-muted">
                          <Lock className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden /> {x}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </Card>
          )
        })}
        <section id="what-we-never-do" className="scroll-mt-24 rounded-2xl bg-brand-950 p-6 text-white sm:p-8">
          <h2 className="text-xl font-bold text-white">What PaperAid never does</h2>
          <ul className="mt-4 grid gap-3 text-sm text-brand-100/90 sm:grid-cols-2">
            {[
              'Invent citations, sources, statistics or participant details',
              'Change your findings or the meaning of your argument',
              'Rewrite your text during a formatting-only job',
              'Promise a score or result on Turnitin or any other detector',
              'Train AI models on your papers',
              'Share your files with anyone outside the services that process them',
            ].map((x) => (
              <li key={x} className="flex gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand-300" /> {x}
              </li>
            ))}
          </ul>
        </section>
      </div>
      <FinalCta />
    </>
  )
}

const FAQ = [
  {
    q: 'How is the price worked out?',
    a: 'Each service has a fixed price in credits that covers a paper of up to 10 pages (about 2,500 words). Longer papers cost more in steps of 10 pages. The credits for a job are reserved when you start it and charged only for what is delivered; if PaperAid cannot deliver, they come back.',
  },
  {
    q: 'Can I be charged more than the price I saw?',
    a: 'No. The credits are held from your balance when you start, and the price you saw is the most you pay.',
  },
  {
    q: 'What if my job fails, or only part of it works?',
    a: "A job that fails costs nothing. If only part of a job can be delivered, for example some passages keep your wording because a change couldn't be verified, you pay only for the part you received, and the rest returns to your balance.",
  },
  { q: 'Do credits expire?', a: 'No. Credits stay in your account until you use them. They can’t be exchanged for cash.' },
  {
    q: 'Can I buy credits now?',
    a: 'Not yet. Buying credits opens when mobile-money payments launch. Until then, beta jobs run without charge.',
  },
  {
    q: 'Do I need an account?',
    a: 'Yes, so your papers and credits stay private to you. We only ask for what we need to run your jobs.',
  },
]

const PRICE_ROWS: { key: string; name: string; note?: string; service: ServiceId }[] = [
  { key: 'AI_CHECK', name: 'Writing check', service: 'AI_CHECK' },
  { key: 'ACADEMIC', name: 'Academic, evidence and method review', note: 'added to a check of academic work', service: 'AI_CHECK' },
  { key: 'REFINE_LIGHT', name: 'Check + Refine, light', service: 'REFINE' },
  { key: 'REFINE', name: 'Check + Refine, standard', service: 'REFINE' },
  { key: 'REDRAFT', name: 'Deep redraft', service: 'REDRAFT' },
  { key: 'SOURCE_CHECK', name: 'Source check', service: 'SOURCE_CHECK' },
  { key: 'TEMPLATE_FORMAT', name: 'University template formatting', service: 'TEMPLATE_FORMAT' },
  { key: 'REVIEW', name: 'Proposal review', service: 'PROPOSAL' },
  { key: 'PLAN', name: 'Proposal plan', note: 'any length', service: 'PROPOSAL' },
  { key: 'CHAPTER_1', name: 'Proposal Chapter One', note: 'any length', service: 'PROPOSAL' },
  { key: 'CHAPTER_2', name: 'Proposal Chapter Two', note: 'any length', service: 'PROPOSAL' },
  { key: 'CHAPTER_3', name: 'Proposal Chapter Three', note: 'any length', service: 'PROPOSAL' },
]

function PriceTable() {
  const { config } = useData()
  const p = config.pricing
  const perPage = (ugx: number) => `${formatTokenNumber(ugx)} credits`
  return (
    <ul className="mt-4 divide-y divide-line rounded-xl border border-line bg-white text-sm">
      {PRICE_ROWS.filter((r) => p.tokens[r.key] !== undefined && config.availability[r.service] !== 'soon').map((r) => (
        <li key={r.key} className="flex items-center justify-between gap-3 px-4 py-2.5">
          <span>
            {r.name}
            {r.note && <span className="block text-xs text-fg-subtle">{r.note}</span>}
          </span>
          <span className="font-semibold whitespace-nowrap">{p.tokens[r.key]} credits</span>
        </li>
      ))}
      <li className="flex items-center justify-between gap-3 px-4 py-2.5">
        <span>
          Academic formatting (APA or Harvard)
          <span className="block text-xs text-fg-subtle">per 300 words, at least {perPage(p.formatMinUgx)}</span>
        </span>
        <span className="font-semibold whitespace-nowrap">{perPage(p.formatUgxPer300Words)}</span>
      </li>
      <li className="flex items-center justify-between gap-3 px-4 py-2.5">
        <span>
          LaTeX conversion
          <span className="block text-xs text-fg-subtle">per 300 words, at least {perPage(p.latexMinUgx)}</span>
        </span>
        <span className="font-semibold whitespace-nowrap">{perPage(p.latexUgxPer300Words)}</span>
      </li>
    </ul>
  )
}

export function PricingPage() {
  useTitle('Pricing')
  const { config } = useData()
  return (
    <>
      <PageHero eyebrow="Pricing" title="Simple prices in credits.">
        No subscription. Buy credits; the credits for a job are reserved when you start it, and you pay only for what is delivered. One credit is UGX{' '}
        {config.ugxPerToken.toLocaleString('en')}.
      </PageHero>
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <PricingModel />
        <div className="mt-14 grid gap-10 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold">Prices</h2>
            <p className="mt-2 text-sm text-fg-muted">
              For a paper of up to {config.pricing.bandPages} pages. Each further {config.pricing.bandPages} pages adds {Math.round(config.pricing.bandStep * 100)}% of the price.
            </p>
            <PriceTable />
          </div>
          <div>
            <h2 className="text-2xl font-bold">Questions</h2>
            <dl className="mt-5 space-y-5">
              {FAQ.map((f) => (
                <div key={f.q}>
                  <dt className="font-semibold">{f.q}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-fg-muted">{f.a}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
      <FinalCta />
    </>
  )
}

export function PrivacyPage() {
  useTitle('Privacy')
  const { config } = useData()
  const sections = [
    { title: 'What we store', body: 'Your email address, the files you upload, the files we produce for you, and basic job details such as dates and what each job cost. For a research proposal, also the study details, plan, chapters and sources you work on, and the title-page details you choose to add. Nothing else is required to use PaperAid.' },
    { title: 'Who processes your paper', body: 'Your text is processed by PaperAid and by the AI providers we use for analysis, writing and review (OpenAI, Anthropic and Google). They process it only to run your job. We use Google’s paid Gemini service, whose terms say your content is not used to improve Google’s products; like the other providers, Google may keep it for a limited time to detect abuse. For research proposals, coursework and funding documents, short search queries about your topic are also sent to web search and to the OpenAlex and Crossref scholarly indexes, never your name or registration number. For academic work, the entries of your reference list are looked up in the same indexes to check the works exist. PaperAid never uses your papers to train AI models.' },
    { title: 'How long we keep it', body: `Files are deleted automatically ${config.retentionDays} days after your job. A research proposal is kept while you work on it and deleted ${config.retentionDays} days after your last change to it; its page shows the date. You can delete a job, a proposal, or your whole account, at any time.` },
    { title: 'Who can see it', body: 'Only you. Our support team can see job details such as status and errors, but not your paper, unless you ask us to look at it.' },
    { title: 'Where it is processed', body: 'PaperAid runs on Google Cloud in Europe. Our AI providers may process text in other countries. By using PaperAid you consent to this transfer.' },
  ]
  return (
    <>
      <PageHero eyebrow="Privacy" title="Your paper is private. Here is exactly how we handle it.">
        A plain-language summary. The full privacy policy will be published before PaperAid leaves beta.
      </PageHero>
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-14 sm:px-6">
        {sections.map((s) => (
          <Card key={s.title} className="p-6">
            <h2 className="text-lg font-semibold">{s.title}</h2>
            <p className="mt-2 leading-relaxed text-fg-muted">{s.body}</p>
          </Card>
        ))}
      </div>
    </>
  )
}
