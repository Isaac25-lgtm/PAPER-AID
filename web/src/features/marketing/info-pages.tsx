import { Check, Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge, Card, Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { AVAILABILITY_BADGE, SERVICES, SERVICE_ORDER } from '../../lib/services'
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
    q: 'Why is there no fixed price list?',
    a: 'Every paper needs different work. A clean two-page essay and a 60-page dissertation full of generic passages cost very different amounts to process, so PaperAid prices each paper from the work it actually needs instead of charging everyone the same.',
  },
  {
    q: 'What does the estimate cost?',
    a: 'Refinement needs a short AI scan to size the work: which passages need attention and how. The most the scan can cost is shown before you start it, you pay only what it actually costs, and it counts toward your job if you go ahead. If the scan fails, it is not charged. AI Check, University templates and APA or Harvard formatting are priced from the length of your paper (and guide) with no scan.',
  },
  {
    q: 'Can the final price be higher than the estimate?',
    a: 'No. Your estimate is the most you will pay. The amount is held from your credits when you approve it, you are charged for the work actually done, and anything unused goes back to your balance.',
  },
  {
    q: 'What if my job fails?',
    a: "You get everything back, including the estimate charge. If our accuracy check can't verify a change, we keep your original wording rather than deliver something altered, and if only part of your paper could be improved, you pay only for that part.",
  },
  { q: 'Do credits expire?', a: 'No. Credits stay in your account until you use them. They can’t be withdrawn as cash.' },
  {
    q: 'Can I buy credits now?',
    a: 'Not yet. Top-ups open when mobile-money payments launch. Until then, beta jobs run without charge.',
  },
  {
    q: 'Do I need an account?',
    a: 'Yes, so your papers and credits stay private to you. We only ask for what we need to run your jobs.',
  },
]

export function PricingPage() {
  useTitle('Pricing')
  const { config } = useData()
  return (
    <>
      <PageHero eyebrow="Pricing" title="Pay for the work your paper needs.">
        No price list and no subscription. Top up credits, see an estimate for your paper before anything runs, and pay for the work it actually needs,
        never more than the estimate.
      </PageHero>
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <PricingModel />
        <div className="mt-14 grid gap-10 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold">How your price is worked out</h2>
            <ol className="mt-5 space-y-4 text-sm leading-relaxed text-fg-muted">
              <li>
                <span className="font-semibold text-fg">1. We read your paper.</span> After upload, PaperAid checks the file and measures how much text
                there is to work on.
              </li>
              <li>
                <span className="font-semibold text-fg">2. We size the work.</span> For refinement, a short AI scan finds the passages that need
                attention; you start it yourself and see its most before it runs. Everything else is priced from length alone.
              </li>
              <li>
                <span className="font-semibold text-fg">3. You approve the estimate.</span> It is the most you will pay, and it is held from your credits
                while the work runs.
              </li>
              <li>
                <span className="font-semibold text-fg">4. You pay for what was done.</span> The final charge reflects the work your paper actually
                needed; the rest of the hold returns to your balance straight away.
              </li>
            </ol>
            <div className="mt-6 rounded-xl border border-line bg-surface-subtle p-4 text-sm">
              <p className="font-semibold">Services</p>
              <ul className="mt-2 space-y-1.5 text-fg-muted">
                {SERVICE_ORDER.map((id) => (
                  <li key={id} className="flex items-center justify-between gap-3">
                    <span>{SERVICES[id].name}</span>
                    {config.availability[id] === 'available' ? (
                      <span className="text-xs font-medium text-brand-700">Priced per paper</span>
                    ) : (
                      <Badge>{AVAILABILITY_BADGE[config.availability[id] as 'soon']}</Badge>
                    )}
                  </li>
                ))}
              </ul>
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
    { title: 'What we store', body: 'Your email address, the files you upload, the files we produce for you, and basic job details such as dates and what each job cost. Nothing else is required to use PaperAid.' },
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
