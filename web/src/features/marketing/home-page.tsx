import { ArrowRight, Ban, ChartColumn, ChevronDown, FilePen, HandCoins, Lock, MapPinned, NotebookPen, Search, ShieldCheck, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { ButtonLink } from '../../components/ui/button'
import { Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { HeroPreview } from './hero-preview'
import { DataLive, FundingLive, MapLive, PaperLive, ResearchLive } from './live-visuals'
import { FinalCta, PricingModel, Reveal } from './sections'

/** The public home page (redesign 2026-10-04): Jenni's calm structure with PaperAid's own content. Every
 *  claim is true of the product today: no university logos, user counts or invented results. */
export function HomePage() {
  useTitle('')
  const { config } = useData()

  const steps = [
    { title: 'Tell us what you need', body: 'Your question or brief, your topic, a funder’s call, a dataset or your own paper. A few questions, nothing else to set up.' },
    { title: 'PaperAid does the work', body: 'It reads what you gave it, finds and confirms sources, writes and checks every requirement, or analyses your data with every number calculated by code.' },
    { title: 'Review and download', body: 'Read the result on screen, ask for changes in your own words, then download Word, PDF or Excel.' },
  ]

  return (
    <>
      <section className="px-4 pt-16 pb-12 sm:px-6 sm:pt-24">
        <Reveal className="mx-auto max-w-3xl text-center">
          <h1 className="text-[2.6rem] leading-[1.05] font-medium tracking-[-0.035em] text-fg sm:text-[3.9rem]">From first idea to finished paper.</h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-fg-muted">
            PaperAid is where researchers and students plan, research, analyse, write, check and format academic work, with every source confirmed and
            every number calculated by code.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <ButtonLink to="/app/new" size="lg" className="shadow-[0_0_0_4px_rgb(63_75_227/0.08),inset_0_1px_0_rgb(255_255_255/0.15)]">
              Get started <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
            <ButtonLink to="/#how-it-works" size="lg" variant="secondary">
              See how it works
            </ButtonLink>
          </div>
          <p className="mt-6 text-[13px] text-fg-subtle">For researchers and students · Your work stays private · Deleted after {config.retentionDays} days</p>
        </Reveal>
        <Reveal className="mx-auto mt-14 max-w-5xl" delay={200}>
          <HeroPreview />
        </Reveal>
      </section>

      <section className="px-4 pb-16 sm:px-6" aria-label="Sections">
        <ul className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-x-8 gap-y-3 text-[15px] text-fg-subtle">
          {[
            { icon: FilePen, label: 'Academic research' },
            { icon: NotebookPen, label: 'Coursework' },
            { icon: HandCoins, label: 'Funding' },
            { icon: ChartColumn, label: 'Data analysis' },
            { icon: MapPinned, label: 'Geospatial analysis' },
            { icon: Search, label: 'Your own paper' },
          ].map((s) => (
            <li key={s.label} className="flex items-center gap-2">
              <s.icon className="size-4" aria-hidden /> {s.label}
            </li>
          ))}
        </ul>
      </section>


      <section className="px-4 py-20 sm:px-6 sm:py-28" aria-labelledby="features-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal>
            <Eyebrow>What PaperAid does</Eyebrow>
            <h2 id="features-title" className="mt-3 text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">Built for serious academic work</h2>
            <p className="mt-3 max-w-2xl text-lg leading-relaxed text-fg-muted">Not a chatbot. Tell PaperAid what you need, press Start, and come back to a document you can review, change and download.</p>
          </Reveal>
          <div className="mt-16 space-y-24">
            <Feature eyebrow="Academic research and coursework" title="Your research from proposal to results, and coursework to your brief"
              body={['A concept paper, then the proposal (Chapters One to Three) written to your institution’s guide; then your data analysed and Chapter Four, the results, written objective by objective. Coursework written to your question and brief.',
                'Every reference is a source PaperAid found and confirmed, in your referencing style. Nothing is cited that it couldn’t check.']}
              visual={<ResearchLive />} />
            <Feature eyebrow="Data analysis" title="Analyse your data without leaving your work" flip
              body={['Describe, compare, relate and correlate, filtered by any variable, with effect sizes and confidence intervals. Themes from interviews and focus groups, every quote checked word for word against its transcript.',
                'Small counts are never shown, and every number is calculated by code, never by a model.']}
              visual={<DataLive />} />
            <Feature eyebrow="Geospatial analysis" title="See where it happens, on official maps"
              body={['Map your records, totals or rates by district, subcounty, sub-region or region, on official boundaries. Zoom to one region or the districts you choose, with their neighbours for context.',
                'Every map comes with its table, and areas with too few records to show safely are hidden.']}
              visual={<MapLive />} />
            <Feature eyebrow="Funding concept notes and proposals" title="From concept note to full proposal, answering everything the call asks" flip
              body={['A concept note for a call or a funder, and the full funding proposal, written to the call. The logframe, workplan and M&E table come from one results model, so they always agree.',
                'Every budget sum is worked out for you. Figures only you can give are marked for you to fill in, never invented.']}
              visual={<FundingLive />} />
            <Feature eyebrow="Your own paper" title="Check, redraft and format the paper you wrote"
              body={['Writing feedback that marks generic or repetitive passages with reasons, a redraft in your own voice when you want one, and formatting in APA, Harvard or your institution’s guide.',
                'Your citations, quotations and numbers are kept exactly as they are.']}
              visual={<PaperLive />} />
          </div>
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-20 bg-surface-subtle px-4 py-20 sm:px-6 sm:py-24" aria-labelledby="how-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal>
            <Eyebrow>How it works</Eyebrow>
            <h2 id="how-title" className="mt-3 max-w-xl text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">From your task to a finished document in three steps</h2>
          </Reveal>
          <ol className="mt-12 grid gap-5 md:grid-cols-3">
            {steps.map((step, i) => (
              <Reveal as="li" key={step.title} delay={i * 120} className="rounded-lg border border-line bg-white p-5">
                <span className="block text-[2.9rem] leading-none font-medium tracking-[-0.04em] text-[#d1d5dc]">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="mt-5 text-xl font-medium tracking-[-0.01em] text-fg">{step.title}</h3>
                <p className="mt-3 text-[15px] leading-relaxed text-fg-subtle">{step.body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="bg-surface-subtle px-4 py-20 sm:px-6 sm:py-24" aria-labelledby="trust-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Eyebrow>Built to protect your work</Eyebrow>
            <h2 id="trust-title" className="mt-3 text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">Your ideas stay yours</h2>
            <p className="mt-3 text-lg leading-relaxed text-fg-muted">PaperAid never invents sources, statistics or participant details, and never changes your findings.</p>
          </Reveal>
          <Reveal className="mx-auto mt-12 max-w-3xl overflow-hidden rounded-xl border border-line bg-white" delay={150}>
            <ul className="divide-y divide-line">
              {[
                { icon: Lock, title: 'Citations locked', body: 'Citations, quotes, numbers and links are protected during editing and checked afterwards.' },
                { icon: ShieldCheck, title: 'Formatting never rewrites', body: 'Formatting is checked automatically to confirm not a single word of yours changed.' },
                { icon: Ban, title: 'Nothing invented', body: 'An accuracy check rejects any change that adds claims, sources or data.' },
                { icon: Trash2, title: `Deleted after ${config.retentionDays} days`, body: 'Your files are private to your account and removed automatically. Delete them sooner any time.' },
              ].map((item) => (
                <li key={item.title} className="flex gap-4 px-6 py-5">
                  <item.icon className="mt-0.5 size-5 shrink-0 text-fg-subtle" aria-hidden />
                  <div>
                    <h3 className="text-base font-medium text-fg">{item.title}</h3>
                    <p className="mt-1 text-[15px] leading-relaxed text-fg-muted">{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="border-t border-line bg-surface-subtle px-6 py-4 text-sm leading-relaxed text-fg-muted">
              {config.availability.AI_CHECK === 'available' ? 'The writing check is feedback on how your paper reads, not an AI detector. ' : 'PaperAid does not detect AI. '}
              No detector, ours or anyone else’s, can prove who wrote a text, and PaperAid never promises a result on another service.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="px-4 py-20 sm:px-6 sm:py-24" aria-labelledby="who-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal>
            <Eyebrow>Who uses PaperAid</Eyebrow>
            <h2 id="who-title" className="mt-3 text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">For students and researchers alike</h2>
            <p className="mt-3 text-lg text-fg-muted">The same workspace, wherever careful, sourced writing matters.</p>
          </Reveal>
          <Reveal as="ul" className="mt-10 flex flex-wrap gap-2.5" delay={120}>
            {['Undergraduate students', 'Master’s and PhD candidates', 'Postgraduate researchers', 'NGO and project teams', 'Research assistants', 'Anyone analysing survey data'].map((who) => (
              <li key={who} className="rounded-full border border-line bg-white px-4 py-2 text-[15px] text-fg-muted">{who}</li>
            ))}
          </Reveal>
          <div className="mt-10">
            <ButtonLink to="/app/new" size="lg">Get started <ArrowRight className="size-4" aria-hidden /></ButtonLink>
          </div>
        </div>
      </section>

      <section className="bg-surface-subtle px-4 py-20 sm:px-6 sm:py-24" aria-labelledby="pricing-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal>
            <Eyebrow>Fair pricing</Eyebrow>
            <h2 id="pricing-title" className="mt-3 text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">Pay for the work your paper needs</h2>
            <p className="mt-3 max-w-2xl text-lg leading-relaxed text-fg-muted">
              No subscription. Each service has a fixed price in credits for your paper’s length, reserved when you start and charged only for what is
              delivered.
            </p>
          </Reveal>
          <div className="mt-10">
            <PricingModel />
          </div>
        </div>
      </section>

      <section className="px-4 py-20 sm:px-6 sm:py-24" aria-labelledby="faq-title">
        <div className="mx-auto max-w-[65rem]">
          <h2 id="faq-title" className="text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">Frequently asked questions</h2>
          <div className="mt-10 space-y-3">
            {[
              ['Does PaperAid detect AI?', `No.${config.availability.AI_CHECK === 'available' ? ' The writing check gives feedback on passages that read as generic, formulaic or repetitive, with reasons.' : ''} No detector can prove who wrote a text, and PaperAid never promises a result on another service.`],
              ['Where do the sources come from?', 'PaperAid searches for sources and cites only those it could confirm. A claim it can’t trace to a confirmed source is left out or marked for you.'],
              ['Is my work private?', `Your files are private to your account and deleted automatically after ${config.retentionDays} days. You can delete them sooner at any time.`],
              ['How are the numbers in my data analysis worked out?', 'By code, never by a model: PaperAid’s statistics engine calculates every number, and the writing explains them. Counts small enough to identify someone are hidden.'],
              ['What does it cost?', 'You pay in PaperAid credits. Each service has a fixed price in credits for your document’s length, reserved when you start and charged only for what is delivered; a job that fails costs nothing.'],
            ].map(([q, a]) => (
              <details key={q} className="group rounded-lg border border-line bg-white shadow-[0_1px_12px_2px_rgb(10_0_31/0.04)]">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 text-lg text-fg [&::-webkit-details-marker]:hidden">
                  {q}
                  <ChevronDown className="size-5 shrink-0 text-fg-subtle transition-transform duration-200 group-open:rotate-180" aria-hidden />
                </summary>
                <p className="px-5 pb-5 text-[15px] leading-relaxed text-fg-muted">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <FinalCta />
    </>
  )
}

function Feature({ eyebrow, title, body, visual, flip = false }: { eyebrow: string; title: string; body: string[]; visual: ReactNode; flip?: boolean }) {
  return (
    <div className="grid items-center gap-10 md:grid-cols-[1fr_1.25fr] md:gap-14">
      <Reveal className={flip ? 'md:order-2' : ''}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <h3 className="mt-3 text-2xl leading-snug font-medium tracking-[-0.015em] text-fg">{title}</h3>
        {body.map((p) => (
          <p key={p} className="mt-4 text-lg leading-relaxed text-fg-muted">{p}</p>
        ))}
      </Reveal>
      <Reveal className={flip ? 'md:order-1' : ''} delay={150}>
        <div className="rounded-lg border border-line bg-surface-muted p-5 sm:p-8" aria-hidden>{visual}</div>
      </Reveal>
    </div>
  )
}
