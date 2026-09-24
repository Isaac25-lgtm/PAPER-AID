import { clsx } from 'clsx'
import { ArrowRight, Check, Lock } from 'lucide-react'
import { LogoMark } from '../../components/layout/logo'

const SUGGESTIONS = [
  { dot: 'bg-amber-400', ring: 'bg-amber-50/80', title: 'Generic phrasing', body: 'Open with a finding from your own data.' },
  { dot: 'bg-violet-500', ring: 'bg-violet-50/80', title: 'Formulaic transition', body: 'Name the concern and who raised it.' },
  { dot: 'bg-sky-500', ring: 'bg-sky-50/80', title: 'Vague claim', body: 'Which studies? Add the source and figure.' },
  { dot: 'bg-brand-500', ring: 'bg-brand-50', title: 'Heading levels', body: 'Two headings typed as bold text — fixed.' },
]

// A product preview built from real components rather than a screenshot, so it
// stays crisp at every size and simplifies itself on small screens.
export function HeroPreview() {
  return (
    <div className="relative" aria-hidden>
      <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-gradient-to-br from-brand-100/80 via-brand-50/40 to-transparent blur-2xl" />
      <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-raised">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <LogoMark className="size-6" />
          <span className="text-sm font-bold">
            Paper<span className="text-brand-600">Aid</span>
          </span>
          <div className="ml-4 hidden gap-4 text-xs font-medium text-fg-subtle sm:flex">
            <span className="border-b-2 border-brand-600 pb-0.5 text-brand-800">Review</span>
            <span>Changes</span>
            <span>Format</span>
          </div>
          <span className="ml-auto grid size-6 place-items-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-800">NA</span>
        </div>

        <div className="grid sm:grid-cols-[1.35fr_1fr]">
          <div className="border-line p-5 sm:border-r sm:p-6">
            <p className="text-[11px] font-semibold tracking-wide text-fg-subtle uppercase">Introduction</p>
            <p className="mt-2 font-serif text-[0.92rem] leading-[1.75] text-fg-muted">
              <mark className="rounded-sm bg-amber-100 px-0.5 text-fg">Social media has become a significant part of students&rsquo; lives in recent years.</mark>{' '}
              It offers channels for class updates and shared notes.{' '}
              <mark className="rounded-sm bg-violet-100 px-0.5 text-fg">However, it can also be a distraction</mark> and may affect performance. Studies
              have shown that <mark className="rounded-sm bg-sky-100 px-0.5 text-fg">excessive use leads to poor grades</mark>{' '}
              <span className="inline-flex items-center gap-0.5 rounded bg-brand-50 px-1 font-sans text-[11px] font-medium text-brand-800 ring-1 ring-brand-200">
                <Lock className="size-2.5" />
                (Kirschner &amp; Karpinski, 2010)
              </span>
              .
            </p>
            <div className="mt-4 rounded-lg border border-brand-200 bg-brand-50/60 p-3">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-800">
                <Check className="size-3" /> Refined
              </p>
              <p className="mt-1 font-serif text-[0.88rem] leading-relaxed text-fg">
                Of the 214 undergraduates surveyed, 187 used social media for over two hours a day — mostly WhatsApp groups for coursework.
              </p>
            </div>
          </div>

          <div className="hidden bg-surface-subtle/60 p-5 sm:block">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold">Suggestions</p>
              <span className="rounded-full bg-brand-700 px-1.5 text-[10px] font-bold text-white">4</span>
            </div>
            <ul className="mt-3 space-y-2">
              {SUGGESTIONS.map((s) => (
                <li key={s.title} className={clsx('rounded-lg p-2.5 ring-1 ring-line', s.ring)}>
                  <p className="flex items-center gap-1.5 text-xs font-semibold text-fg">
                    <span className={clsx('size-2 rounded-full', s.dot)} />
                    {s.title}
                  </p>
                  <p className="mt-0.5 pl-3.5 text-[11px] text-fg-muted">{s.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line bg-white px-5 py-3.5">
          <div>
            <p className="text-[10px] font-medium tracking-wide text-fg-subtle uppercase">Estimated AI-likeness</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-sm font-semibold">
              <span className="text-rose-600">High</span>
              <ArrowRight className="size-3.5 text-fg-subtle" />
              <span className="text-amber-600">Moderate</span>
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium tracking-wide text-fg-subtle uppercase">Citations</p>
            <p className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-brand-700">
              <Lock className="size-3.5" /> 24 of 24 intact
            </p>
          </div>
          <div className="ml-auto hidden rounded-full bg-brand-700 px-3 py-1 text-xs font-semibold text-white md:block">APA 7th applied</div>
        </div>
      </div>
    </div>
  )
}
