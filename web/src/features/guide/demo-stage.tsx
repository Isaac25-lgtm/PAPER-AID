import { clsx } from 'clsx'
import { Pause, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { DemoElement, DemoScene } from './scenes'

/* A section's walkthrough (owner, 2026-11-15, after PaperAid Pro's guides): a small sketch of the page in which a ghost
   pointer moves to each element, types or clicks, and the page reacts. Scenes are data (`scenes.ts`), so a guide is
   written, not coded. Drawn with the app's own tokens, so it follows night mode. Reduced motion: the finished state. */

interface StageState {
  hidden: Set<string>
  labels: Record<string, string>
  typed: Record<string, string>
  selected: Set<string>
  pointer: { x: number; y: number; visible: boolean; click: boolean; instant: boolean }
}

function initial(scene: DemoScene): StageState {
  return {
    hidden: new Set(scene.elements.filter((e) => e.hidden).map((e) => e.id)),
    labels: {},
    typed: {},
    selected: new Set(),
    pointer: { x: 0, y: 0, visible: false, click: false, instant: true },
  }
}

/** Where the scene ends: shown still to people who prefer reduced motion. */
function finalState(scene: DemoScene): StageState {
  const state = initial(scene)
  for (const f of scene.frames) {
    f.reveal?.forEach((id) => state.hidden.delete(id))
    f.hide?.forEach((id) => state.hidden.add(id))
    Object.assign(state.labels, f.set ?? {})
    if (f.to && f.type) state.typed[f.to] = f.type
    if (f.select) state.selected = new Set(f.select)
  }
  return state
}

function reducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function Element({ el, state, refFor }: { el: DemoElement; state: StageState; refFor: (id: string) => (node: HTMLElement | null) => void }) {
  if (state.hidden.has(el.id)) return null
  const label = state.labels[el.id] ?? el.text
  const typed = state.typed[el.id]
  const selected = state.selected.has(el.id)
  const common = { ref: refFor(el.id) }
  const appear = 'animate-[fadein_.25s_ease-out_both]'
  switch (el.kind) {
    case 'input':
      return (
        <div {...common} className={clsx(appear, 'flex min-w-0 items-center rounded-lg border bg-surface px-2.5 py-1.5 text-[12px]', typed ? 'border-line-strong' : 'border-line', el.grow && 'flex-1')}>
          <span className={clsx('truncate', typed ? 'text-fg' : 'text-fg-subtle')}>{typed || label}</span>
          {typed !== undefined && <span className="ml-px inline-block h-3.5 w-px animate-pulse bg-fg" />}
        </div>
      )
    case 'button':
    case 'accent':
      return (
        <div {...common} className={clsx(appear, 'shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-medium whitespace-nowrap',
          el.kind === 'accent' ? 'bg-brand-600 text-white' : selected ? 'bg-fg text-surface' : 'border border-line bg-surface text-fg-muted')}>
          {label}
        </div>
      )
    case 'card':
      return (
        <div {...common} className={clsx(appear, 'rounded-lg border bg-surface px-3 py-2', selected ? 'border-brand-300 ring-2 ring-brand-100' : 'border-line')}>
          <p className="line-clamp-2 text-[12.5px] leading-snug text-fg">{label}</p>
          {el.sub && <p className="mt-0.5 truncate text-[11px] text-fg-subtle">{el.sub}</p>}
        </div>
      )
    case 'check':
      return (
        <div {...common} className={clsx(appear, 'flex items-center gap-2 text-[12.5px] text-fg-muted')}>
          <span className={clsx('flex size-4 shrink-0 items-center justify-center rounded border text-[10px]', selected ? 'border-fg bg-fg text-surface' : 'border-line-strong bg-surface')}>{selected ? '✓' : ''}</span>
          <span className={clsx(selected && 'text-fg')}>{label}</span>
        </div>
      )
    case 'chip':
      return (
        <div {...common} className={clsx('animate-[fadein_.3s_ease-out_both] self-start rounded-md px-2 py-1 text-[11px] font-medium', selected ? 'bg-emerald-50 text-emerald-800' : 'bg-brand-50 text-brand-700')}>
          {label}
        </div>
      )
    case 'note':
      return (
        <div {...common} className={clsx(appear, 'rounded-lg border border-dashed px-3 py-2 text-[12px] leading-snug', selected ? 'border-brand-300 bg-brand-50 text-fg' : 'border-line-strong bg-surface-subtle text-fg-muted')}>
          {label}
        </div>
      )
    default:
      return <p {...common} className="text-[10.5px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">{label}</p>
  }
}

/** The ghost pointer, drawn like the home page's. */
function Pointer({ x, y, visible, click, instant }: StageState['pointer']) {
  return (
    <div className={clsx('pointer-events-none absolute top-0 left-0 z-20', !instant && 'transition-transform duration-[700ms] ease-[cubic-bezier(0.45,0.05,0.2,1)]', visible ? 'opacity-100' : 'opacity-0')}
      style={{ transform: `translate(${x}px, ${y}px)` }}>
      <span className={clsx('absolute -top-3 -left-3 size-6 rounded-full bg-brand-500/35 transition-all duration-200', click ? 'scale-100 opacity-100' : 'scale-0 opacity-0')} />
      <svg width="18" height="18" viewBox="0 0 24 24" className={clsx('relative drop-shadow-md transition-transform duration-150', click && 'scale-90')}>
        <path d="M4 2.5 19.5 11l-6.8 1.9L9.4 19.6Z" fill="#101828" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** Plays a scene in a loop while mounted, reporting the guide step shown. One caption per frame. */
export function DemoStage({ scene, narration, onStep }: { scene: DemoScene; narration: string[]; onStep?: (step: number) => void }) {
  const [reduced] = useState(reducedMotion)
  const [state, setState] = useState<StageState>(() => (reduced ? finalState(scene) : initial(scene)))
  const [frame, setFrame] = useState(reduced ? -1 : 0)
  const [paused, setPaused] = useState(false)
  const stage = useRef<HTMLDivElement>(null)
  const nodes = useRef(new Map<string, HTMLElement>())
  const stepRef = useRef(onStep)
  useEffect(() => {
    stepRef.current = onStep
  }, [onStep])
  const refFor = (id: string) => (node: HTMLElement | null) => {
    if (node) nodes.current.set(id, node)
    else nodes.current.delete(id)
  }

  useEffect(() => {
    if (reduced || paused) return
    let cancelled = false
    let timer: number | undefined
    const sleep = (ms: number) =>
      new Promise<void>((resolve, reject) => {
        timer = window.setTimeout(() => (cancelled ? reject(new Error('stopped')) : resolve()), ms)
      })
    const point = (id?: string) => {
      const box = stage.current?.getBoundingClientRect()
      const r = id ? nodes.current.get(id)?.getBoundingClientRect() : undefined
      if (!box || !r) return { x: (box?.width ?? 380) - 40, y: (box?.height ?? 220) - 30 }
      return { x: r.left - box.left + Math.min(r.width * 0.5, 60), y: r.top - box.top + r.height * 0.55 }
    }
    const update = (fn: (s: StageState) => StageState) =>
      setState((s) => fn({ ...s, hidden: new Set(s.hidden), selected: new Set(s.selected), labels: { ...s.labels }, typed: { ...s.typed } }))
    const run = async () => {
      for (;;) {
        setState(initial(scene))
        setFrame(0)
        stepRef.current?.(0)
        await sleep(500)
        const start = point()
        update((s) => ({ ...s, pointer: { ...start, visible: true, click: false, instant: true } }))
        await sleep(300)
        for (const [index, f] of scene.frames.entries()) {
          stepRef.current?.(f.step)
          setFrame(index)
          if (f.to) {
            const target = point(f.to)
            update((s) => ({ ...s, pointer: { ...target, visible: true, click: false, instant: false } }))
            await sleep(800)
          }
          if (f.to && f.type) {
            const id = f.to
            for (let i = 1; i <= f.type.length; i++) {
              const value = f.type.slice(0, i)
              update((s) => ({ ...s, typed: { ...s.typed, [id]: value } }))
              await sleep(38)
            }
            await sleep(250)
          }
          if (f.click) {
            update((s) => ({ ...s, pointer: { ...s.pointer, click: true } }))
            await sleep(220)
            update((s) => ({ ...s, pointer: { ...s.pointer, click: false } }))
          }
          update((s) => {
            f.hide?.forEach((id) => s.hidden.add(id))
            f.reveal?.forEach((id) => s.hidden.delete(id))
            Object.assign(s.labels, f.set ?? {})
            if (f.select) s.selected = new Set(f.select)
            return s
          })
          await sleep(1500)
        }
        update((s) => ({ ...s, pointer: { ...s.pointer, visible: false } }))
        await sleep(2400)
      }
    }
    run().catch(() => undefined) // stopped: the guide closed or paused
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [scene, paused, reduced])

  const area = (name: DemoElement['area']) => scene.elements.filter((e) => e.area === name).map((el) => <Element key={el.id} el={el} state={state} refFor={refFor} />)
  return (
    <div>
      <div ref={stage} aria-hidden className="relative overflow-hidden rounded-xl border border-line-strong bg-surface-subtle">
        <div className="flex items-center gap-1.5 border-b border-line bg-surface px-3 py-2">
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="ml-2 text-[11px] font-medium text-fg-subtle">{scene.title}</span>
        </div>
        <div className="flex min-h-[40px] items-center gap-2 border-b border-line bg-surface px-3 py-2">{area('bar')}</div>
        <div className="grid min-h-[130px] grid-cols-[1fr_130px] gap-2.5 p-2.5">
          <div className="flex min-w-0 flex-col gap-2">{area('main')}</div>
          <div className="flex min-w-0 flex-col gap-2">{area('side')}</div>
        </div>
        <Pointer {...state.pointer} />
      </div>
      <p className="mt-2 flex items-start gap-2 rounded-lg bg-fg px-3 py-1.5 text-[12.5px] leading-snug text-surface" aria-live="polite">
        {!reduced && <span className="mt-px shrink-0 font-mono text-[10.5px] text-brand-300">{Math.max(frame, 0) + 1}/{scene.frames.length}</span>}
        <span key={frame} className="flex-1 animate-[fadein_.25s_ease-out_both]">{frame >= 0 ? narration[frame] : narration.join(' ')}</span>
        {!reduced && (
          <button type="button" onClick={() => setPaused(!paused)} aria-pressed={paused} aria-label={paused ? 'Play the walkthrough' : 'Pause the walkthrough'}
            className="shrink-0 rounded p-0.5 text-surface/80 hover:bg-surface/10 hover:text-surface">
            {paused ? <Play className="size-3.5" aria-hidden /> : <Pause className="size-3.5" aria-hidden />}
          </button>
        )}
      </p>
    </div>
  )
}
