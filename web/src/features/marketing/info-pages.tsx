import { Check, Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge, Card, Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { formatUGX } from '../../lib/format'
import { AVAILABILITY_BADGE, SERVICES, SERVICE_ORDER } from '../../lib/services'
import { useTitle } from '../../lib/use-title'
import { FinalCta, PricingCards } from './sections'

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
      <PageHero eyebrow="Features" title="Every service, and exactly what it changes.">
        Each PaperAid service has a defined job. You always know what will be changed, what will be left alone and what you get back.
      </PageHero>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-14 sm:px-6">
        {SERVICE_ORDER.map((id) => {
          const s = SERVICES[id]
          const availability = config.availability[id]
          return (
            <Card key={id} className="p-6 sm:p-8">
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
                  <p className="mt-4 text-xs text-fg-subtle">
                    Accepts: {s.accepts}
                    <br />
                    From {formatUGX(config.indicativeFrom[id])}
                  </p>
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
    q: 'Why does the price depend on length?',
    a: 'Longer papers take more checking and more careful editing. Your quote is calculated from your word count and the services you pick, and it stays fixed once you submit.',
  },
  {
    q: 'What if my job fails?',
    a: "If a job fails on our side you are not charged — or, once payments are live, you get a free re-run. If our accuracy check can't verify a change, we keep your original wording rather than deliver something altered.",
  },
  { q: 'Is it free right now?', a: 'Yes. During the beta every job is free. You will still see the price your job would cost, which helps us set fair prices.' },
  {
    q: 'Do I need an account?',
    a: 'Yes — so your papers stay private to you. Sign up with email or Google. We only ask for what we need to run your jobs.',
  },
]

export function PricingPage() {
  useTitle('Pricing')
  const { config } = useData()
  return (
    <>
      <PageHero eyebrow="Pricing" title="Pay per paper. Know the price before you start.">
        Prices depend on your paper&rsquo;s length and the services you choose. You see the exact amount after upload — no subscriptions.
        {!config.paymentsEnabled && ' During the beta, every job is free.'}
      </PageHero>
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <PricingCards />
        <div className="mt-14 grid gap-10 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold">How your quote is calculated</h2>
            <ol className="mt-5 space-y-4 text-sm text-fg-muted">
              <li>
                <span className="font-semibold text-fg">1. We read your file.</span> After upload we count analysable words and check the format.
              </li>
              <li>
                <span className="font-semibold text-fg">2. Each service has a base price plus a rate per 1,000 words.</span> Refinement costs more than a
                check because it rewrites and double-checks passages.
              </li>
              <li>
                <span className="font-semibold text-fg">3. The total is fixed for 30 minutes.</span> If you change the file or the services, you get a new
                quote.
              </li>
            </ol>
            <div className="mt-6 overflow-hidden rounded-xl border border-line">
              <table className="w-full text-sm">
                <caption className="sr-only">Starting prices by service</caption>
                <thead className="bg-surface-subtle text-left text-xs text-fg-subtle">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Service</th>
                    <th className="px-4 py-2.5 text-right font-medium">From</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {SERVICE_ORDER.map((id) => (
                    <tr key={id}>
                      <td className="px-4 py-2.5">
                        {SERVICES[id].name} {config.availability[id] !== 'available' && <Badge className="ml-1">{AVAILABILITY_BADGE[config.availability[id] as 'soon']}</Badge>}
                      </td>
                      <td className="px-4 py-2.5 text-right font-medium">{formatUGX(config.indicativeFrom[id])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
    { title: 'What we store', body: 'Your email address, the files you upload, the files we produce for you, and basic job details such as dates and prices. Nothing else is required to use PaperAid.' },
    { title: 'Who processes your paper', body: 'Your text is processed by PaperAid and by the AI providers we use for analysis and editing (OpenAI and Anthropic). They process it only to run your job. PaperAid never uses your papers to train AI models.' },
    { title: 'How long we keep it', body: `Files are deleted automatically ${config.retentionDays} days after your job. You can delete a job, or your whole account, at any time from your dashboard.` },
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
