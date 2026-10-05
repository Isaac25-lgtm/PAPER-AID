import { clsx } from 'clsx'
import { BookCheck, Check, Download, Lock } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

/* Live illustrations for the home page's features (owner 2026-10-04: "live and representative of the stuff it is
   representing", with a ghost cursor). Each is a short scripted loop built from the product's own elements, with
   example content, that runs only while it is on screen; with reduced motion it shows one finished frame. */

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

interface Step {
  ms: number // how long this step lasts
  at?: string // the element (data-at) the cursor moves to
  click?: boolean
}

/** The current step of a looping script, advancing only while the stage is on screen. */
function useScript(stage: React.RefObject<HTMLDivElement | null>, steps: Step[], still: number) {
  const [reduced] = useState(prefersReducedMotion)
  const [on, setOn] = useState(false)
  const [step, setStep] = useState(0)
  useEffect(() => {
    const el = stage.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const seen = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { threshold: 0.3 })
    seen.observe(el)
    return () => seen.disconnect()
  }, [stage])
  useEffect(() => {
    if (!on || reduced) return
    const t = window.setTimeout(() => setStep((s) => (s + 1) % steps.length), steps[step].ms)
    return () => window.clearTimeout(t)
  }, [on, reduced, step, steps])
  return reduced ? still : step
}

/** The ghost cursor: glides to the element named by the step and presses it when the step clicks. */
function Ghost({ stage, step }: { stage: React.RefObject<HTMLDivElement | null>; step: Step }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const [pressed, setPressed] = useState(false)
  useLayoutEffect(() => {
    const root = stage.current
    const target = step.at ? root?.querySelector<HTMLElement>(`[data-at="${step.at}"]`) : null
    if (!root || !target) return
    const r = target.getBoundingClientRect()
    const b = root.getBoundingClientRect()
    setPos({ x: r.left - b.left + Math.min(r.width * 0.55, 60), y: r.top - b.top + r.height * 0.55 })
  }, [stage, step])
  useEffect(() => {
    if (!step.click) return
    const press = window.setTimeout(() => setPressed(true), 650)
    const lift = window.setTimeout(() => setPressed(false), 850)
    return () => {
      window.clearTimeout(press)
      window.clearTimeout(lift)
    }
  }, [step])
  if (!pos) return null
  return (
    <div className="pointer-events-none absolute top-0 left-0 z-20 transition-transform duration-[650ms] ease-[cubic-bezier(0.45,0.05,0.2,1)]"
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}>
      <span className={clsx('absolute -top-3 -left-3 size-6 rounded-full bg-brand-500/35 transition-all duration-200', pressed ? 'scale-100 opacity-100' : 'scale-0 opacity-0')} />
      <svg width="18" height="18" viewBox="0 0 24 24" className={clsx('relative drop-shadow-md transition-transform duration-150', pressed && 'scale-90')}>
        <path d="M4 2.5 19.5 11l-6.8 1.9L9.4 19.6Z" fill="#101828" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** Text that types itself in while `active`, and stays once typed. */
function Typed({ text, active, done, className }: { text: string; active: boolean; done: boolean; className?: string }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!active) {
      setN(done ? text.length : 0)
      return
    }
    setN(0)
    const t = window.setInterval(() => setN((k) => (k >= text.length ? k : k + 1)), 24)
    return () => window.clearInterval(t)
  }, [active, done, text])
  return (
    <span className={className}>
      {text.slice(0, n)}
      {active && n < text.length && <span className="ml-px inline-block h-[1em] w-[1.5px] translate-y-[2px] animate-pulse bg-brand-600" />}
    </span>
  )
}

function Window({ title, stage, cursor, children }: { title: string; stage: React.RefObject<HTMLDivElement | null>; cursor: Step; children: ReactNode }) {
  return (
    <div ref={stage} className="relative overflow-hidden rounded-md bg-white shadow-[0_1px_3px_rgb(0_0_0/0.06)]">
      <div className="flex items-center gap-1.5 border-b border-line bg-surface-subtle px-3 py-2">
        <span className="size-2 rounded-full bg-[#ff6159]" /><span className="size-2 rounded-full bg-[#ffbd2e]" /><span className="size-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 text-[11px] font-medium text-fg-muted">{title}</span>
      </div>
      {children}
      <Ghost stage={stage} step={cursor} />
    </div>
  )
}

function Lines({ widths, shown = widths.length }: { widths: number[]; shown?: number }) {
  return (
    <div className="space-y-2">
      {widths.map((w, i) => (
        <div key={i} className={clsx('h-2 rounded-full bg-surface-muted transition-opacity duration-500', i < shown ? 'opacity-100' : 'opacity-0')} style={{ width: `${w}%` }} />
      ))}
    </div>
  )
}

const pill = (active: boolean) => clsx('rounded-md px-2 py-1 transition-colors duration-300', active ? 'bg-brand-50 text-brand-700' : 'text-fg-subtle')

// --- Academic research: a chapter written from confirmed sources, then the results chapter from the data -------------

const RESEARCH: Step[] = [
  { ms: 1300, at: 'write' }, { ms: 700, at: 'write', click: true }, { ms: 3600, at: 'text' }, { ms: 1200, at: 'ch4' }, { ms: 700, at: 'ch4', click: true }, { ms: 3200, at: 'table' },
]

export function ResearchLive() {
  const stage = useRef<HTMLDivElement>(null)
  const step = useScript(stage, RESEARCH, 5)
  const results = step >= 5
  return (
    <Window title="Malaria vaccine uptake in Mukono" stage={stage} cursor={RESEARCH[step]}>
      <div className="flex gap-1 border-b border-line px-3 py-2 text-[11px] font-medium">
        <span className={pill(false)}>Plan</span>
        <span className={pill(!results)}>Chapter One</span>
        <span data-at="ch4" className={pill(results)}>Chapter Four · Results</span>
      </div>
      <div className="h-[16rem] p-4">
        {!results ? (
          <>
            <p className="text-[13px] font-semibold text-fg">1.1 Background to the study</p>
            <p data-at="text" className="mt-3 min-h-[3.4rem] font-serif text-[12.5px] leading-relaxed text-fg">
              <Typed active={step === 2} done={step > 2 && step < 5} text="A trial in seven African countries found that RTS,S reduced clinical malaria, with greater efficacy when a booster dose was given " />
              {step >= 3 && step < 5 && <a href="https://pubmed.ncbi.nlm.nih.gov/25913272/" target="_blank" rel="noopener noreferrer" tabIndex={-1} className="rounded bg-brand-50 px-1 font-sans text-[11px] text-brand-700">(RTS,S Clinical Trials Partnership, 2015)</a>}
            </p>
            <p className={clsx('mt-2 flex items-center gap-1 text-[11px] text-emerald-700 transition-opacity duration-500', step >= 3 && step < 5 ? 'opacity-100' : 'opacity-0')}>
              <BookCheck className="size-3.5" /> Source confirmed
            </p>
            <div className="mt-3"><Lines widths={[94, 88, 70]} shown={step >= 3 ? 3 : 0} /></div>
            <div className="mt-4 flex justify-end">
              <span data-at="write" className={clsx('rounded-md px-2.5 py-1 text-[11px] font-medium text-white transition-colors', step === 1 ? 'bg-brand-700' : 'bg-brand-600')}>Write Chapter One</span>
            </div>
          </>
        ) : (
          <div data-at="table" className="animate-[fadein_.5s_ease-out]">
            <p className="text-[13px] font-semibold text-fg">4.2 Objective 1: Uptake by distance to a facility</p>
            <p className="mt-2 text-[11px] font-medium text-fg">Table 4.1. Children fully vaccinated, by distance</p>
            <table className="mt-1.5 w-full text-[11px]">
              <thead><tr className="border-b border-line text-left text-fg-subtle"><th className="py-1 font-medium">Distance</th><th className="font-medium">n</th><th className="font-medium">Vaccinated</th></tr></thead>
              <tbody className="text-fg">
                <tr className="border-b border-line"><td className="py-1">Under 5 km</td><td>212</td><td>71.2%</td></tr>
                <tr className="border-b border-line"><td className="py-1">5 km or more</td><td>148</td><td>52.7%</td></tr>
              </tbody>
            </table>
            <p className="mt-3 font-serif text-[12px] leading-relaxed text-fg-muted">Uptake was higher among caregivers living under 5 km from a facility (χ²(1) = 12.4, p &lt; .001).</p>
            <p className="mt-2 text-[10px] text-fg-subtle">Illustrative data · not study findings</p>
          </div>
        )}
      </div>
    </Window>
  )
}

// --- Data analysis: a comparison run, explained, added to the report ------------------------------------------------------

const DATA: Step[] = [{ ms: 1100, at: 'compare' }, { ms: 700, at: 'compare', click: true }, { ms: 1900, at: 'chart' }, { ms: 1600, at: 'stats' }, { ms: 900, at: 'add' }, { ms: 700, at: 'add', click: true }, { ms: 2200, at: 'add' }]

export function DataLive() {
  const stage = useRef<HTMLDivElement>(null)
  const step = useScript(stage, DATA, 6)
  const run = step >= 2
  const bars = [{ label: 'Female', h: 74 }, { label: 'Male', h: 61 }]
  return (
    <Window title="Data Lab · example data" stage={stage} cursor={DATA[step]}>
      <div className="flex flex-wrap gap-1.5 border-b border-line px-3 py-2 text-[11px] font-medium">
        <span className="rounded-md border border-line px-2 py-1 text-fg-subtle">Describe</span>
        <span data-at="compare" className={clsx('rounded-md border px-2 py-1 transition-colors', step >= 1 ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-line text-fg-subtle')}>Compare two groups</span>
        <span className="rounded-md border border-line px-2 py-1 text-fg-subtle">Relate</span>
        <span className="rounded-md border border-line px-2 py-1 text-fg-subtle">Map</span>
      </div>
      <div className="h-[16rem] p-4">
        <p className="text-[12px] font-medium text-fg">Exam score by sex</p>
        <div data-at="chart" className="mt-2 flex h-20 items-end gap-8 border-b border-line px-8">
          {bars.map((b) => (
            <div key={b.label} className="flex h-full flex-1 flex-col justify-end">
              <div className="w-full rounded-t-sm bg-brand-500/85 transition-[height] duration-700 ease-out" style={{ height: run ? `${b.h}%` : '0%' }} />
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-8 px-8 text-center text-[10px] text-fg-subtle">{bars.map((b) => <span key={b.label} className="flex-1">{b.label}</span>)}</div>
        <div data-at="stats" className={clsx('mt-2.5 flex flex-wrap gap-1.5 text-[11px] transition-opacity duration-500', step >= 3 ? 'opacity-100' : 'opacity-0')}>
          <span className="rounded border border-line px-2 py-1 text-fg">Difference 4.2 (95% CI 1.1 to 7.3)</span>
          <span className="rounded border border-line px-2 py-1 text-fg">Hedges’ g 0.31</span>
          <span className="rounded border border-line px-2 py-1 text-fg">p = .008</span>
        </div>
        <div className="mt-2.5 flex items-center justify-between">
          <span className={clsx('flex items-center gap-1 text-[11px] text-emerald-700 transition-opacity duration-300', step >= 6 ? 'opacity-100' : 'opacity-0')}><Check className="size-3.5" /> Added to your report</span>
          <span data-at="add" className={clsx('rounded-md px-2.5 py-1 text-[11px] font-medium text-white transition-colors', step === 5 ? 'bg-brand-700' : 'bg-brand-600')}>Add to report</span>
        </div>
      </div>
    </Window>
  )
}

// --- Geospatial: maps of several countries, cycling, with the same look --------------------------------------------------

const MAPS = [
  { file: 'uga', label: 'Uganda by district', note: 'Official UBOS boundaries. Shading illustrative.' },
  { file: 'ken', label: 'Kenya by county', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'nga', label: 'Nigeria by state', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'ind', label: 'India by state', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'tza', label: 'Tanzania by region', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'bra', label: 'Brazil by state', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'gha', label: 'Ghana by region', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
  { file: 'zaf', label: 'South Africa by province', note: 'Shading illustrative. PaperAid maps Uganda today; more countries are being added.' },
]
const MAP_STEPS: Step[] = MAPS.flatMap(() => [{ ms: 1500, at: 'legend-hi' }, { ms: 2600, at: 'map-hot' }])

export function MapLive() {
  const stage = useRef<HTMLDivElement>(null)
  const step = useScript(stage, MAP_STEPS, 0)
  const index = Math.floor(step / 2) % MAPS.length
  const shades = ['#3f4be3', '#5562ef', '#7886f7', '#a3affc', '#c9d0fe', '#e3e7ff']
  return (
    <Window title="Map · example data" stage={stage} cursor={MAP_STEPS[step]}>
      <div className="relative h-[16rem] p-4">
        <div className="grid h-[12.4rem] grid-cols-[1fr_auto] items-center gap-4">
          <div className="relative h-full">
            {MAPS.map((m, i) => (
              <img key={m.file} src={`/maps/${m.file}.svg`} alt="" loading="lazy"
                className={clsx('absolute inset-0 m-auto max-h-full max-w-full transition-opacity duration-700', i === index ? 'opacity-100' : 'opacity-0')} />
            ))}
            <span data-at="map-hot" className="absolute top-[38%] left-[46%] size-1" />
            <span className={clsx('absolute top-[30%] left-[50%] rounded bg-fg px-1.5 py-0.5 text-[10px] text-white shadow transition-opacity duration-300', step % 2 === 1 ? 'opacity-100' : 'opacity-0')}>
              Higher than most areas
            </span>
          </div>
          <div className="space-y-1 text-[10px] text-fg-subtle">
            {shades.map((c, i) => (
              <p key={c} data-at={i === 0 ? 'legend-hi' : undefined} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: c }} /> {i === 0 ? 'Highest' : i === 5 ? 'Lowest' : ''}</p>
            ))}
          </div>
        </div>
        <p className="mt-1 text-[11px] font-medium text-fg">{MAPS[index].label}</p>
        <p className="text-[10px] text-fg-subtle">{MAPS[index].note}</p>
      </div>
    </Window>
  )
}

// --- Funding: what the call asks, checked; the applicant's own figure added without AI ------------------------------------

const FUNDING: Step[] = [{ ms: 900 }, { ms: 600 }, { ms: 600 }, { ms: 600 }, { ms: 900, at: 'gap' }, { ms: 700, at: 'gap', click: true }, { ms: 1800, at: 'save' }, { ms: 700, at: 'save', click: true }, { ms: 2400, at: 'save' }]

export function FundingLive() {
  const stage = useRef<HTMLDivElement>(null)
  const step = useScript(stage, FUNDING, 8)
  const items = ['Problem statement', 'Results framework with indicators', 'Workplan and M&E plan', 'Budget (every sum worked out)']
  const filled = step >= 8
  return (
    <Window title="What the call asks" stage={stage} cursor={FUNDING[step]}>
      <ul className="h-[16rem] space-y-1.5 p-3.5 text-[12px]">
        {items.map((item, i) => (
          <li key={item} className="flex items-center justify-between rounded border border-line px-3 py-1.5">
            <span className="flex items-center gap-2 text-fg"><span className={clsx('size-1.5 rounded-full transition-colors', step > i ? 'bg-emerald-500' : 'bg-line-strong')} /> {item}</span>
            <span className={clsx('text-emerald-600 transition-opacity duration-300', step > i ? 'opacity-100' : 'opacity-0')}>Met</span>
          </li>
        ))}
        <li data-at="gap" className={clsx('rounded border px-3 py-1.5 transition-colors', step >= 5 && !filled ? 'border-brand-300 bg-brand-50/40' : 'border-line')}>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-fg"><span className={clsx('size-1.5 rounded-full', filled ? 'bg-emerald-500' : 'bg-amber-400')} /> Baseline: facility deliveries</span>
            <span className={filled ? 'text-emerald-600' : 'text-amber-600'}>{filled ? 'Met' : 'For you to add'}</span>
          </div>
          {step >= 6 && (
            <div className="mt-1.5 flex items-center gap-2">
              <span className="flex-1 rounded border border-line bg-white px-2 py-1 font-mono text-[11px] text-fg"><Typed active={step === 6} done={step > 6} text="42%" /></span>
              <span data-at="save" className={clsx('rounded-md px-2 py-1 text-[11px] font-medium text-white', step === 7 ? 'bg-brand-700' : 'bg-brand-600')}>{filled ? 'Saved' : 'Save'}</span>
            </div>
          )}
          {filled && <p className="mt-1 text-[10px] text-fg-subtle">Your figure, placed in every table that uses it. No AI involved.</p>}
        </li>
      </ul>
    </Window>
  )
}

// --- Your own paper: a passage marked, redrafted in your voice, then formatted -----------------------------------------------

const PAPER: Step[] = [{ ms: 1600 }, { ms: 900, at: 'mark' }, { ms: 700, at: 'mark', click: true }, { ms: 1000, at: 'redraft' }, { ms: 700, at: 'redraft', click: true }, { ms: 2600, at: 'mark' }, { ms: 900, at: 'format' }, { ms: 700, at: 'format', click: true }, { ms: 2600, at: 'format' }]

export function PaperLive() {
  const stage = useRef<HTMLDivElement>(null)
  const step = useScript(stage, PAPER, 8)
  const scanned = step >= 1
  const open = step >= 3 && step <= 4
  const rewriting = step === 5
  const rewritten = step >= 5
  const formatted = step >= 8
  return (
    <Window title="Your paper" stage={stage} cursor={PAPER[step]}>
      <div className="relative h-[16rem] p-4">
        <div className="flex items-center justify-between">
          <p className={clsx('text-[12px] font-semibold text-fg transition-all', formatted && 'tracking-tight')}>{formatted ? '1. Introduction' : 'Introduction'}</p>
          <span data-at="format" className={clsx('rounded-md border px-2 py-0.5 text-[10px] font-medium transition-colors', formatted ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : step === 7 ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-line text-fg-subtle')}>
            {formatted ? 'APA 7th applied' : 'Format'}
          </span>
        </div>
        <p className={clsx('mt-3 font-serif text-[12.5px] text-fg-muted transition-all duration-500', formatted ? 'leading-[2]' : 'leading-relaxed')}>
          {rewritten ? (
            <span data-at="mark" className={clsx('rounded-sm px-0.5 text-fg', rewriting && 'bg-brand-50')}>
              <Typed active={rewriting} done={rewritten && !rewriting} text="Access to clean water still shapes child health in rural districts." />
            </span>
          ) : (
            <mark data-at="mark" className={clsx('rounded-sm px-0.5 text-fg transition-colors duration-500', scanned ? 'bg-amber-100' : 'bg-transparent', open && 'ring-2 ring-amber-300')}>
              In today’s world, access to clean water is a very important issue for everyone.
            </mark>
          )}{' '}
          Households far from a protected source report more diarrhoeal illness{' '}
          <span className="inline-flex items-center gap-0.5 rounded bg-brand-50 px-1 font-sans text-[10.5px] text-brand-700"><Lock className="size-2.5" /> (Wolf et al., 2018)</span>.{' '}
          <mark className={clsx('rounded-sm px-0.5 transition-colors duration-500', scanned ? 'bg-violet-100 text-fg' : 'bg-transparent')}>Furthermore, it is also worth noting that</mark> distance limits how much water a household collects.
        </p>
        <div className={clsx('absolute right-4 bottom-4 left-4 rounded-md border border-amber-200 bg-white p-2.5 shadow-raised transition-all duration-300', open ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-2 opacity-0')}>
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-amber-800"><span className="size-1.5 rounded-full bg-amber-400" /> Generic phrasing</p>
          <p className="mt-0.5 text-[11px] text-fg-muted">Say it plainly and specifically, in your own voice.</p>
          <span data-at="redraft" className={clsx('mt-2 inline-flex rounded-md px-2 py-0.5 text-[10.5px] font-medium text-white', step === 4 ? 'bg-brand-700' : 'bg-brand-600')}>Redraft this</span>
        </div>
        <p className={clsx('absolute bottom-4 left-4 flex items-center gap-1 text-[10.5px] text-fg-subtle transition-opacity duration-300', step >= 6 ? 'opacity-100' : 'opacity-0')}>
          <Download className="size-3" /> Citations, quotes and numbers kept exactly
        </p>
      </div>
    </Window>
  )
}
