import { ArrowRight, Ban, BookCheck, ChartColumn, ChevronDown, FilePen, HandCoins, Lock, NotebookPen, Search, ShieldCheck, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { ButtonLink } from '../../components/ui/button'
import { Eyebrow } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { HeroPreview } from './hero-preview'
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
            { icon: NotebookPen, label: 'Coursework' },
            { icon: FilePen, label: 'Research proposals' },
            { icon: HandCoins, label: 'Funding' },
            { icon: ChartColumn, label: 'Data analysis' },
            { icon: Search, label: 'Your own paper' },
          ].map((s) => (
            <li key={s.label} className="flex items-center gap-2">
              <s.icon className="size-4" aria-hidden /> {s.label}
            </li>
          ))}
        </ul>
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

      <section className="px-4 py-20 sm:px-6 sm:py-28" aria-labelledby="features-title">
        <div className="mx-auto max-w-[65rem]">
          <Reveal>
            <Eyebrow>What PaperAid does</Eyebrow>
            <h2 id="features-title" className="mt-3 text-[2rem] leading-[1.15] tracking-[-0.025em] sm:text-[2.5rem]">Built for serious academic work</h2>
            <p className="mt-3 max-w-2xl text-lg leading-relaxed text-fg-muted">Not a chatbot. Tell PaperAid what you need, press Start, and come back to a document you can review, change and download.</p>
          </Reveal>
          <div className="mt-16 space-y-24">
            <Feature eyebrow="Coursework and proposals" title="Written to your brief, from sources it confirmed"
              body={['Coursework, research proposals (Chapters One to Three) and concept papers, written to your question and your institution’s guide.',
                'Every reference is a source PaperAid found and confirmed, in your referencing style. Nothing is cited that it couldn’t check.']}
              visual={<DocVisual />} />
            <Feature eyebrow="Data Lab" title="Analyse your data without leaving your work" flip
              body={['Describe, compare, relate and correlate, filtered by any variable, with effect sizes and confidence intervals. Maps of Uganda by district, subcounty, sub-region or region. Themes from interviews, every quote checked word for word.',
                'Small counts are never shown, and every number is calculated by code, never by a model.']}
              visual={<DataVisual />} />
            <Feature eyebrow="Funding" title="Proposals that answer everything the call asks"
              body={['Concept notes and full funding proposals, written to the call. The logframe, workplan and M&E table come from one results model, so they always agree.',
                'Every budget sum is worked out for you. Figures only you can give are marked for you to fill in, never invented.']}
              visual={<ChecklistVisual />} />
            <Feature eyebrow="Your own paper" title="Check, redraft and format the paper you wrote" flip
              body={['Writing feedback that marks generic or repetitive passages with reasons, a redraft in your own voice when you want one, and formatting in APA, Harvard or your institution’s guide.',
                'Your citations, quotations and numbers are kept exactly as they are.']}
              visual={<ReviewVisual />} />
          </div>
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
              The writing check is feedback on how your paper reads, not an AI detector. No detector, ours or anyone else’s, can prove who wrote a text,
              and PaperAid never promises a result on another service.
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
              ['Does PaperAid detect AI?', 'No. The writing check gives feedback on passages that read as generic, formulaic or repetitive, with reasons. No detector can prove who wrote a text, and PaperAid never promises a result on another service.'],
              ['Where do the sources come from?', 'PaperAid searches for sources and cites only those it could confirm. A claim it can’t trace to a confirmed source is left out or marked for you.'],
              ['Is my work private?', `Your files are private to your account and deleted automatically after ${config.retentionDays} days. You can delete them sooner at any time.`],
              ['How are the numbers in my data analysis worked out?', 'By code, never by a model: PaperAid’s statistics engine calculates every number, and the writing explains them. Counts small enough to identify someone are hidden.'],
              ['What does it cost?', 'Each service has a fixed price in credits for your document’s length. Credits are reserved when you start and charged only for what is delivered; a job that fails costs nothing.'],
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

/* Illustrations built from the product's own elements, with placeholder lines for text: they show the
   shape of the work, never a real student's document or results. */
function Window({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-md bg-white shadow-[0_1px_3px_rgb(0_0_0/0.06)]">
      <div className="flex items-center gap-1.5 border-b border-line bg-surface-subtle px-3 py-2">
        <span className="size-2 rounded-full bg-[#ff6159]" /><span className="size-2 rounded-full bg-[#ffbd2e]" /><span className="size-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 text-[11px] font-medium text-fg-muted">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

function Lines({ widths }: { widths: number[] }) {
  return (
    <div className="space-y-2">
      {widths.map((w, i) => <div key={i} className="h-2 rounded-full bg-surface-muted" style={{ width: `${w}%` }} />)}
    </div>
  )
}

function DocVisual() {
  return (
    <Window title="Chapter One">
      <p className="text-[13px] font-semibold text-fg">1.1 Background to the study</p>
      <div className="mt-3"><Lines widths={[96, 90, 94, 60]} /></div>
      <p className="mt-4 flex flex-wrap items-center gap-1.5 text-[11px] text-fg-muted">
        <span className="rounded bg-brand-50 px-1.5 py-0.5 text-brand-700">(Author, 2023)</span>
        <span className="flex items-center gap-1"><BookCheck className="size-3.5 text-emerald-600" /> Source confirmed</span>
      </p>
      <div className="mt-3"><Lines widths={[92, 88, 70]} /></div>
    </Window>
  )
}

function DataVisual() {
  const bars = [62, 88, 45, 74, 30]
  return (
    <Window title="Data Lab · example data">
      <p className="text-[12px] font-medium text-fg">Score by group</p>
      <div className="mt-4 flex h-28 items-end gap-3 border-b border-line px-2">
        {bars.map((h, i) => <div key={i} className="flex-1 rounded-t-sm bg-brand-500/80" style={{ height: `${h}%` }} />)}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        {[['Groups', '5'], ['95% CI', 'shown'], ['Small counts', 'hidden']].map(([k, v]) => (
          <div key={k} className="rounded border border-line px-2 py-1.5"><p className="text-fg-subtle">{k}</p><p className="font-medium text-fg">{v}</p></div>
        ))}
      </div>
    </Window>
  )
}

function ChecklistVisual() {
  return (
    <Window title="What the call asks">
      <ul className="space-y-2.5 text-[12px]">
        {[['Problem statement', true], ['Results framework with indicators', true], ['Workplan and M&E plan', true], ['Budget (sums worked out)', true], ['Your baseline figures', false]].map(([item, done]) => (
          <li key={String(item)} className="flex items-center justify-between rounded border border-line px-3 py-2">
            <span className="flex items-center gap-2 text-fg"><span className={`size-1.5 rounded-full ${done ? 'bg-emerald-500' : 'bg-amber-400'}`} /> {item}</span>
            <span className={done ? 'text-emerald-600' : 'text-amber-600'}>{done ? 'Met' : 'For you to add'}</span>
          </li>
        ))}
      </ul>
    </Window>
  )
}

function ReviewVisual() {
  return (
    <Window title="Writing feedback">
      <div className="space-y-2">
        <div className="rounded border border-amber-200 bg-amber-50/70 p-2.5"><p className="text-[11px] font-medium text-amber-800">Generic phrasing</p><div className="mt-2"><Lines widths={[90, 72]} /></div></div>
        <div className="rounded border border-line p-2.5"><Lines widths={[94, 88, 64]} /></div>
        <div className="rounded border border-violet-200 bg-violet-50/70 p-2.5"><p className="text-[11px] font-medium text-violet-800">Repetitive structure</p><div className="mt-2"><Lines widths={[86, 58]} /></div></div>
      </div>
    </Window>
  )
}
