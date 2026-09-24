import { clsx } from 'clsx'
import { Check, Flag, Lock } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { LogoMark } from '../../components/layout/logo'

// A live product preview: PaperAid scans a paragraph, raises suggestions, and a ghost cursor
// accepts them while the rewrite types itself in. Built from real components rather than a
// video so it stays crisp at every size. It only ever rewrites phrasing and flags the vague
// claim for the student to source, exactly as the product does; it never invents facts.

interface Suggestion {
  title: string
  body: string
  dot: string
  mark: string
  open: string
  proposal?: string
  note?: string
  action?: string
}

const SUGGESTIONS: Suggestion[] = [
  {
    title: 'Generic phrasing',
    body: 'Say it plainly and specifically.',
    dot: 'bg-amber-400',
    mark: 'bg-amber-100',
    open: 'bg-amber-50 ring-amber-300',
    proposal: 'Social media is now part of students’ daily routine.',
    action: 'Accept',
  },
  {
    title: 'Formulaic transition',
    body: 'Drop the stock “However” opener.',
    dot: 'bg-violet-500',
    mark: 'bg-violet-100',
    open: 'bg-violet-50 ring-violet-300',
    proposal: 'The same apps also pull attention away from study',
    action: 'Accept',
  },
  {
    title: 'Vague claim',
    body: 'Which studies? Name your source.',
    dot: 'bg-sky-500',
    mark: 'bg-sky-100',
    open: 'bg-sky-50 ring-sky-300',
    note: 'PaperAid never invents sources. This one is yours to add.',
    action: 'Got it',
  },
  { title: 'Heading levels', body: 'Two headings typed as bold text.', dot: 'bg-brand-500', mark: '', open: '' },
]

const ORIGINAL = [
  'Social media has become a significant part of students’ lives in recent years.',
  'However, it can also be a distraction',
  'excessive use leads to poor grades',
]

interface Cursor {
  x: number
  y: number
  visible: boolean
  pressed: boolean
}

interface Scene {
  scanning: boolean
  found: number
  open: number | null
  typing: number | null
  typed: number
  done: [boolean, boolean, boolean]
  improved: boolean
  formatted: boolean
  fading: boolean
  cursor: Cursor
}

const HIDDEN_CURSOR: Cursor = { x: 0, y: 0, visible: false, pressed: false }
const START: Scene = { scanning: true, found: 0, open: null, typing: null, typed: 0, done: [false, false, false], improved: false, formatted: false, fading: false, cursor: HIDDEN_CURSOR }
const FINAL: Scene = { ...START, scanning: false, found: 4, done: [true, true, true], improved: true, formatted: true }
const TYPE_MS = 32

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export function HeroPreview() {
  const stageRef = useRef<HTMLDivElement>(null)
  const cardRefs = useRef<(HTMLLIElement | null)[]>([])
  const actionRefs = useRef<(HTMLSpanElement | null)[]>([])
  const segmentRefs = useRef<(HTMLElement | null)[]>([])
  const [reduced] = useState(prefersReducedMotion)
  const [scene, setScene] = useState<Scene>(reduced ? FINAL : START)
  const [visible, setVisible] = useState(false)
  const [cycle, setCycle] = useState(0)

  // Only animate while the preview is on screen.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.25 })
    observer.observe(stage)
    return () => observer.disconnect()
  }, [])

  // The scripted timeline. Positions are measured from the real elements at each step, so the
  // cursor lands correctly at any width; where the suggestions column is hidden (phones) the
  // cursor stays hidden and the text still animates.
  useEffect(() => {
    if (reduced || !visible) return
    const timers: number[] = []
    const at = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms))
    const update = (patch: Partial<Scene> | ((s: Scene) => Partial<Scene>)) =>
      setScene((s) => ({ ...s, ...(typeof patch === 'function' ? patch(s) : patch) }))

    const pointAt = (el: HTMLElement | null | undefined): Cursor | null => {
      const stage = stageRef.current
      if (!stage || !el) return null
      const target = el.getBoundingClientRect()
      if (target.width === 0) return null
      const base = stage.getBoundingClientRect()
      return { x: target.left - base.left + target.width * 0.6, y: target.top - base.top + target.height * 0.55, visible: true, pressed: false }
    }
    const moveTo = (el: () => HTMLElement | null | undefined) => update((s) => ({ cursor: pointAt(el()) ?? { ...s.cursor, visible: false } }))
    const press = (then: (s: Scene) => Partial<Scene>) => {
      update((s) => ({ ...then(s), cursor: { ...s.cursor, pressed: true } }))
      timers.push(window.setTimeout(() => update((s) => ({ cursor: { ...s.cursor, pressed: false } })), 180))
    }
    const parkCursor = () => {
      const stage = stageRef.current
      const box = stage?.getBoundingClientRect()
      return { x: (box?.width ?? 400) * 0.82, y: (box?.height ?? 400) + 24, visible: false, pressed: false }
    }

    const accept = (i: 0 | 1, start: number) => {
      at(start, () => moveTo(() => cardRefs.current[i]))
      at(start + 800, () => press(() => ({ open: i })))
      at(start + 1500, () => moveTo(() => actionRefs.current[i]))
      at(start + 2200, () => press(() => ({ open: null, typing: i, typed: 0 })))
      at(start + 2600, () => moveTo(() => segmentRefs.current[i])) // watch the rewrite type in
      return start + 2200 + ((SUGGESTIONS[i].proposal ?? '').length + 12) * TYPE_MS
    }

    at(0, () => setScene({ ...START, cursor: parkCursor() }))
    at(1800, () => update({ scanning: false, found: 1 }))
    at(2250, () => update({ found: 2 }))
    at(2700, () => update({ found: 3 }))
    at(3150, () => update({ found: 4 }))
    at(3500, () => update((s) => ({ cursor: { ...s.cursor, visible: true } })))
    const afterFirst = accept(0, 3700)
    const afterSecond = accept(1, afterFirst + 300)
    const flag = afterSecond + 300
    at(flag, () => moveTo(() => cardRefs.current[2]))
    at(flag + 800, () => press(() => ({ open: 2 })))
    at(flag + 1500, () => moveTo(() => actionRefs.current[2]))
    at(flag + 2200, () => press((s) => ({ open: null, done: [s.done[0], s.done[1], true] })))
    at(flag + 2600, () => moveTo(() => segmentRefs.current[2]))
    at(flag + 2900, () => update({ improved: true, formatted: true, cursor: parkCursor() }))
    at(flag + 6200, () => update({ fading: true }))
    at(flag + 6900, () => setCycle((c) => c + 1))
    return () => timers.forEach(window.clearTimeout)
  }, [reduced, visible, cycle])

  // Types the accepted rewrite in, one character at a time.
  useEffect(() => {
    if (scene.typing === null) return
    const i = scene.typing
    const text = SUGGESTIONS[i].proposal ?? ''
    if (scene.typed >= text.length) {
      const t = window.setTimeout(
        () =>
          setScene((s) => {
            const done: Scene['done'] = [...s.done]
            done[i] = true
            return { ...s, typing: null, done }
          }),
        250,
      )
      return () => window.clearTimeout(t)
    }
    const t = window.setTimeout(() => setScene((s) => ({ ...s, typed: s.typed + 1 })), TYPE_MS)
    return () => window.clearTimeout(t)
  }, [scene.typing, scene.typed])

  const resolved = (i: number) => (i < 3 ? scene.done[i] : scene.formatted)
  const remaining = SUGGESTIONS.filter((_, i) => i < scene.found && !resolved(i)).length

  const segment = (i: 0 | 1 | 2) => {
    const s = SUGGESTIONS[i]
    const rewriting = scene.typing === i
    if (i < 2 && (rewriting || scene.done[i])) {
      const text = s.proposal ?? ''
      return (
        <span
          ref={(el) => {
            segmentRefs.current[i] = el
          }}
          className={clsx('rounded-sm px-0.5 text-fg transition-colors duration-1000', rewriting ? 'bg-brand-100' : 'bg-transparent')}
        >
          {rewriting ? text.slice(0, scene.typed) : text}
          {rewriting && <span className="ml-px inline-block h-[1.05em] w-[2px] translate-y-[3px] animate-pulse bg-brand-600" />}
        </span>
      )
    }
    const shown = scene.found > i
    const flagged = i === 2 && scene.done[2]
    return (
      <mark
        ref={(el) => {
          segmentRefs.current[i] = el
        }}
        className={clsx(
          'rounded-sm px-0.5 transition-all duration-500',
          flagged ? 'bg-transparent text-fg underline decoration-sky-500 decoration-dashed decoration-2 underline-offset-4' : shown ? `${s.mark} text-fg` : 'bg-transparent text-inherit',
          scene.open === i && 'ring-2 ring-offset-1 ring-brand-400',
        )}
      >
        {ORIGINAL[i]}
      </mark>
    )
  }

  return (
    <div className="relative" aria-hidden>
      <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-gradient-to-br from-brand-100/80 via-brand-50/40 to-transparent blur-2xl" />
      <div
        ref={stageRef}
        className={clsx('relative overflow-hidden rounded-2xl border border-line bg-white shadow-raised transition-opacity duration-700', scene.fading && 'opacity-40')}
      >
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <LogoMark className="size-6" />
          <span className="text-sm font-bold">
            Paper<span className="text-brand-600">Aid</span>
          </span>
          <div className="ml-4 hidden gap-4 text-xs font-medium text-fg-subtle sm:flex">
            {['Review', 'Changes', 'Format'].map((tab) => {
              const active = tab === (scene.formatted ? 'Format' : 'Review')
              return (
                <span key={tab} className={clsx('border-b-2 pb-0.5 transition-colors duration-500', active ? 'border-brand-600 text-brand-800' : 'border-transparent')}>
                  {tab}
                </span>
              )
            })}
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-medium text-fg-subtle">
            <span className={clsx('size-1.5 rounded-full', scene.scanning ? 'animate-pulse bg-amber-400' : 'bg-brand-500')} />
            {scene.scanning ? 'Analysing…' : scene.formatted ? 'Reviewed' : 'Reviewing'}
          </span>
        </div>

        <div className="grid sm:grid-cols-[1.35fr_1fr]">
          <div className="relative overflow-hidden border-line p-5 sm:border-r sm:p-6">
            {scene.scanning && (
              <div className="pointer-events-none absolute inset-x-0 top-0 h-16 animate-[paperaid-scan_1.7s_ease-in-out_infinite] bg-gradient-to-b from-transparent via-brand-200/50 to-transparent" />
            )}
            <p className="text-[11px] font-semibold tracking-wide text-fg-subtle uppercase">{scene.formatted ? '1. Introduction' : 'Introduction'}</p>
            <p className="mt-2 font-serif text-[0.92rem] leading-[1.8] text-fg-muted">
              {segment(0)} It offers channels for class updates and shared notes. {segment(1)} and may affect performance. Studies have shown that{' '}
              {segment(2)}{' '}
              <span
                className={clsx(
                  'inline-flex items-center gap-0.5 rounded bg-brand-50 px-1 font-sans text-[11px] font-medium text-brand-800 ring-1 transition-all duration-300',
                  scene.open === 2 ? 'ring-2 ring-brand-500' : 'ring-brand-200',
                )}
              >
                <Lock className="size-2.5" />
                (Kirschner &amp; Karpinski, 2010)
              </span>
              .
            </p>
            <p className="mt-4 flex items-center gap-1.5 text-[11px] text-fg-subtle">
              <Lock className="size-3 text-brand-600" /> Citations and numbers are locked while PaperAid edits.
            </p>
          </div>

          <div className="hidden bg-surface-subtle/60 p-5 sm:block">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold">{scene.scanning ? 'Reading your paper…' : 'Suggestions'}</p>
              <span className={clsx('rounded-full px-1.5 text-[10px] font-bold text-white transition-colors', remaining ? 'bg-brand-700' : 'bg-brand-500')}>{remaining}</span>
            </div>
            <ul className="mt-3 space-y-2">
              {SUGGESTIONS.map((s, i) => {
                const isOpen = scene.open === i
                const isDone = resolved(i)
                return (
                  <li
                    key={s.title}
                    ref={(el) => {
                      cardRefs.current[i] = el
                    }}
                    className={clsx(
                      'rounded-lg p-2.5 ring-1 transition-all duration-500',
                      scene.found > i ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0',
                      isOpen ? `${s.open} shadow-card` : 'bg-white/80 ring-line',
                      isDone && !isOpen && 'opacity-60',
                    )}
                  >
                    <p className="flex items-center gap-1.5 text-xs font-semibold text-fg">
                      {isDone ? (
                        i === 2 ? (
                          <Flag className="size-3 text-sky-600" />
                        ) : (
                          <Check className="size-3 text-brand-600" />
                        )
                      ) : (
                        <span className={clsx('size-2 rounded-full', s.dot)} />
                      )}
                      {s.title}
                      {isDone && <span className="ml-auto text-[10px] font-medium text-fg-subtle">{i === 2 ? 'Flagged' : 'Fixed'}</span>}
                    </p>
                    <p className="mt-0.5 pl-3.5 text-[11px] text-fg-muted">{s.body}</p>
                    {isOpen && (
                      <div className="mt-2 pl-3.5">
                        {s.proposal && <p className="font-serif text-[11px] leading-snug text-fg">&ldquo;{s.proposal}&rdquo;</p>}
                        {s.note && <p className="text-[11px] leading-snug text-fg">{s.note}</p>}
                        <span
                          ref={(el) => {
                            actionRefs.current[i] = el
                          }}
                          className="mt-2 inline-flex rounded-md bg-brand-700 px-2 py-1 text-[10px] font-semibold text-white"
                        >
                          {s.action}
                        </span>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line bg-white px-5 py-3.5">
          <div>
            <p className="text-[10px] font-medium tracking-wide text-fg-subtle uppercase">Estimated AI-likeness</p>
            <p className="mt-0.5 text-sm font-semibold">
              {scene.scanning ? (
                <span className="text-fg-subtle">Checking…</span>
              ) : (
                <span className={clsx('transition-colors duration-700', scene.improved ? 'text-amber-600' : 'text-rose-600')}>{scene.improved ? 'Moderate' : 'High'}</span>
              )}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium tracking-wide text-fg-subtle uppercase">Citations</p>
            <p className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-brand-700">
              <Lock className="size-3.5" /> Intact
            </p>
          </div>
          <div
            className={clsx(
              'ml-auto hidden items-center gap-1 rounded-full bg-brand-700 px-3 py-1 text-xs font-semibold text-white transition-all duration-500 md:flex',
              scene.formatted ? 'scale-100 opacity-100' : 'scale-90 opacity-0',
            )}
          >
            <Check className="size-3.5" /> APA 7th applied
          </div>
        </div>

        <div
          className="pointer-events-none absolute top-0 left-0 z-20 transition-[transform,opacity] duration-700 ease-[cubic-bezier(0.45,0.05,0.2,1)]"
          style={{ transform: `translate(${scene.cursor.x}px, ${scene.cursor.y}px)`, opacity: scene.cursor.visible ? 1 : 0 }}
        >
          <span
            className={clsx(
              'absolute -top-3 -left-3 size-6 rounded-full bg-brand-500/35 transition-all duration-300',
              scene.cursor.pressed ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
            )}
          />
          <svg width="20" height="20" viewBox="0 0 24 24" className={clsx('relative drop-shadow-md transition-transform duration-150', scene.cursor.pressed && 'scale-85')}>
            <path d="M4 2.5 19.5 11l-6.8 1.9L9.4 19.6Z" fill="#12261c" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
          <span className="absolute top-4 left-4 rounded-full bg-brand-700 px-1.5 py-0.5 text-[9px] font-semibold whitespace-nowrap text-white shadow-card">
            You
          </span>
        </div>
      </div>
    </div>
  )
}
