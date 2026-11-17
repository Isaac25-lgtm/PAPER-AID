import { clsx } from 'clsx'
import { ArrowLeft, ArrowRight, ChevronDown, ChevronUp, Play } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Dialog } from '../../components/ui/overlays'
import { DemoStage } from './demo-stage'
import { GUIDES, NARRATION, SCENES, type GuideKey } from './scenes'

/* Guidance (owner, 2026-11-17, adopted from PaperAid Pro): a "How it works" panel on each section, the Help centre with
   every section's guide, and an optional welcome tour. Nothing opens by itself except a section's own panel the first
   time it is visited on a computer; closing it is remembered (per section, in this browser). */

/** The narrowest window with room for the guide beside the page (sidebar 248 + content 1152 + guide 420 + margins). */
const GUIDE_BESIDE = 1880

const ORDER: GuideKey[] = ['dashboard', 'coursework', 'research-concept', 'proposal', 'funding-concept', 'funding-proposal', 'paper-check', 'formatting']

function stored(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null // storage can be blocked: the default applies
  }
}

function store(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // storage can be blocked: the choice lasts until the page is closed
  }
}

interface Guidance {
  openHelp: (section?: GuideKey) => void
  openTour: () => void
}

const Context = createContext<Guidance>({ openHelp: () => undefined, openTour: () => undefined })

export function useGuidance(): Guidance {
  return useContext(Context)
}

/** Holds the Help centre and the tour for the whole signed-in app. */
export function GuidanceProvider({ children }: { children: ReactNode }) {
  const [help, setHelp] = useState<{ open: boolean; section: GuideKey }>({ open: false, section: 'dashboard' })
  const [tour, setTour] = useState(false)
  const value = useMemo<Guidance>(() => ({
    openHelp: (section) => setHelp({ open: true, section: section ?? 'dashboard' }),
    openTour: () => {
      setHelp((h) => ({ ...h, open: false }))
      setTour(true)
    },
  }), [])
  const closeTour = useCallback(() => {
    store('paperaid.tour', 'seen')
    setTour(false)
  }, [])
  return (
    <Context.Provider value={value}>
      {children}
      <HelpCentre open={help.open} section={help.section} onSection={(section) => setHelp({ open: true, section })} onClose={() => setHelp((h) => ({ ...h, open: false }))} onTour={value.openTour} />
      <Tour open={tour} onClose={closeTour} />
    </Context.Provider>
  )
}

/** Whether the person has finished or skipped the tour in this browser (the dashboard stops offering it). */
export function tourSeen(): boolean {
  return stored('paperaid.tour') === 'seen'
}

function Steps({ section, current }: { section: GuideKey; current?: number }) {
  const guide = GUIDES[section]
  return (
    <ol className="space-y-1.5">
      {guide.steps.map((item, index) => (
        <li key={item.title} aria-current={index === current ? 'step' : undefined}
          className={clsx('flex gap-2.5 rounded-lg px-2 py-1.5 text-[13px] transition-colors', index === current && 'bg-surface-muted')}>
          <span className={clsx('mt-px flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
            index === current ? 'bg-brand-600 text-white' : 'bg-surface-muted text-fg-muted ring-1 ring-line')}>{index + 1}</span>
          <span className="min-w-0">
            <span className="font-medium text-fg">{item.title}.</span> <span className="text-fg-muted">{item.detail}</span>
            {item.action && <Link to={item.action.to} className="ml-1 font-medium whitespace-nowrap text-brand-700 hover:underline">{item.action.label} →</Link>}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** "How <section> works", pinned to the bottom right of a section's page; collapses to a small button. Open the first
 *  time only on a screen wide enough for it to sit beside the page, and whatever the person last chose after that. */
export function SectionGuide({ section }: { section: GuideKey }) {
  const guide = GUIDES[section]
  const key = `paperaid.guide.${section}`
  const [collapsed, setCollapsedState] = useState(() => {
    const saved = stored(key)
    if (saved) return saved === 'collapsed'
    // Open by itself only where it covers nothing: beside the page on a very wide screen (Codex audit 2026-11-17: at
    // 1024 and 1280 px it covered the page's own controls). Elsewhere it starts as the small button.
    return typeof window === 'undefined' || window.innerWidth < GUIDE_BESIDE
  })
  const [step, setStep] = useState(0)
  const [tips, setTips] = useState(false)
  const setCollapsed = (value: boolean) => {
    store(key, value ? 'collapsed' : 'open')
    setCollapsedState(value)
  }

  if (collapsed) {
    return (
      <button type="button" onClick={() => setCollapsed(false)} aria-expanded={false}
        className="fixed right-4 bottom-4 z-30 flex items-center gap-2 rounded-full border border-line-strong bg-surface py-2 pr-4 pl-2 text-sm font-medium text-fg shadow-raised transition-colors hover:border-brand-300 focus-visible:outline-2 focus-visible:outline-brand-600">
        <span className="flex size-6 items-center justify-center rounded-full bg-fg text-surface"><Play className="size-3" aria-hidden /></span>
        How {guide.title} works
      </button>
    )
  }
  return (
    <section aria-label={`How ${guide.title} works`}
      className="fixed inset-x-3 bottom-3 z-30 max-h-[min(74vh,640px)] overflow-y-auto rounded-2xl border border-line-strong bg-surface shadow-raised sm:inset-x-auto sm:right-4 sm:w-[420px]">
      <div className="flex items-start gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-[10.5px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Guide · {guide.title}</p>
          <p className="mt-0.5 text-[15px] font-semibold text-fg">How {guide.title} works</p>
          <p className="mt-0.5 text-[13px] leading-snug text-fg-muted">{guide.summary}</p>
        </div>
        <button type="button" onClick={() => setCollapsed(true)} aria-expanded
          className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-fg-muted hover:bg-surface-muted hover:text-fg">
          <ChevronDown className="size-3.5" aria-hidden /> Collapse
        </button>
      </div>
      <div className="space-y-3 p-4">
        <DemoStage scene={SCENES[section]} narration={NARRATION[section]} onStep={setStep} />
        <Steps section={section} current={step} />
        {guide.tips.length > 0 && (
          <div className="border-t border-line pt-2">
            <button type="button" onClick={() => setTips(!tips)} aria-expanded={tips} className="flex items-center gap-1 text-xs font-medium text-fg-muted hover:text-fg">
              {tips ? <ChevronUp className="size-3.5" aria-hidden /> : <ChevronDown className="size-3.5" aria-hidden />} Good to know
            </button>
            {tips && <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-fg-muted">{guide.tips.map((t) => <li key={t}>{t}</li>)}</ul>}
          </div>
        )}
      </div>
    </section>
  )
}

/** Every section's guide in one place, opened from Help in the left panel. */
function HelpCentre({ open, section, onSection, onClose, onTour }: { open: boolean; section: GuideKey; onSection: (s: GuideKey) => void; onClose: () => void; onTour: () => void }) {
  const guide = GUIDES[section]
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Help" size="wide"
      description="How each part of PaperAid works. Each section also has its own guide at the bottom right of its page.">
      <div className="grid gap-5 sm:grid-cols-[11rem_minmax(0,1fr)]">
        <nav aria-label="Help topics" className="flex gap-1 overflow-x-auto sm:flex-col">
          {ORDER.map((k) => (
            <button key={k} type="button" onClick={() => onSection(k)} aria-current={k === section ? 'page' : undefined}
              className={clsx('shrink-0 rounded-lg px-2.5 py-1.5 text-left text-sm font-medium whitespace-nowrap transition-colors',
                k === section ? 'bg-brand-50 text-brand-700' : 'text-fg-muted hover:bg-surface-muted hover:text-fg')}>
              {GUIDES[k].title}
            </button>
          ))}
        </nav>
        <div className="min-w-0 space-y-3">
          <div>
            <h3 className="text-base font-semibold text-fg">{guide.title}</h3>
            <p className="mt-0.5 text-sm text-fg-muted">{guide.summary}</p>
          </div>
          <DemoStage key={section} scene={SCENES[section]} narration={NARRATION[section]} />
          <Steps section={section} />
          {guide.tips.length > 0 && <ul className="list-disc space-y-1 border-t border-line pt-3 pl-5 text-xs text-fg-muted">{guide.tips.map((t) => <li key={t}>{t}</li>)}</ul>}
          <button type="button" onClick={onTour} className="text-sm font-medium text-brand-700 hover:underline">Take the tour of PaperAid</button>
        </div>
      </div>
    </Dialog>
  )
}

/** The optional welcome tour: each section in turn, with its walkthrough. Offered on the dashboard and in Help, never
 *  opened by itself; finishing or skipping it is remembered in this browser. */
function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [index, setIndex] = useState(0)
  const section = ORDER[index]
  const guide = GUIDES[section]
  const last = index === ORDER.length - 1
  const close = () => {
    setIndex(0)
    onClose()
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()} title={`${index + 1} of ${ORDER.length} · ${guide.title}`} size="wide" description={guide.summary}
      footer={
        <>
          <Button variant="ghost" onClick={close}>Skip the tour</Button>
          {index > 0 && <Button variant="secondary" onClick={() => setIndex(index - 1)}><ArrowLeft className="size-4" aria-hidden /> Back</Button>}
          <Button onClick={() => (last ? close() : setIndex(index + 1))}>{last ? 'Finish the tour' : <>Next <ArrowRight className="size-4" aria-hidden /></>}</Button>
        </>
      }>
      <div className="space-y-3">
        <DemoStage key={section} scene={SCENES[section]} narration={NARRATION[section]} />
        <Steps section={section} />
      </div>
    </Dialog>
  )
}
