import { clsx } from 'clsx'
import { ChevronRight, FolderOpen, Plus } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Alert, Card, EmptyState, Skeleton } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { startChoices, type StartChoice } from '../../lib/start'
import { useTitle } from '../../lib/use-title'
import { useAuth } from '../auth/auth-context'
import { StatusChip } from '../workspace/parts'
import { KINDS, SECTION_LISTS, useYourWork, type WorkItem } from './your-work-data'

function ItemRow({ item }: { item: WorkItem }) {
  return (
    <li>
      <Link to={item.to} className="group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-brand-600">
        <item.icon className="size-[18px] shrink-0 text-fg-subtle" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg group-hover:text-brand-700">{item.title}</p>
          <p className="mt-0.5 truncate text-xs text-fg-subtle">
            {item.kind} · {new Date(item.updated).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <StatusChip status={item.status} />
      </Link>
    </li>
  )
}

function ItemList({ items }: { items: WorkItem[] }) {
  return (
    <Card className="p-1">
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <ItemRow key={item.key} item={item} />
        ))}
      </ul>
    </Card>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

/** Where "Your own paper" keeps its list: paper checks and formatting are jobs, with their own history. */
const PAPERS = '/app/history'

/** The counts on the dashboard's "Your work" card, by where each piece stands. */
const STANDING: { label: string; tones: WorkItem['status']['tone'][] }[] = [
  { label: 'being written', tones: ['running'] },
  { label: 'need you', tones: ['input', 'danger'] },
  { label: 'ready', tones: ['ready', 'warn'] },
]

/** One piece of recent work in "Continue writing": what it is, when it changed and where it stands. */
function ContinueRow({ item }: { item: WorkItem }) {
  return (
    <li>
      <Link to={item.to} className="group flex items-center gap-3 rounded-xl px-3 py-3 transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-brand-600">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-subtle text-fg-muted group-hover:text-brand-600">
          <item.icon className="size-[18px]" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-fg group-hover:text-brand-700">{item.title}</span>
          <span className="mt-0.5 block truncate text-xs text-fg-subtle">
            {item.kind} · {new Date(item.updated).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </span>
        </span>
        <span className="hidden sm:block"><StatusChip status={item.status} /></span>
        <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
      </Link>
    </li>
  )
}

/** One thing that can be started: a plus, its name and what it gives. */
function StartTile({ choice, wide = false }: { choice: StartChoice; wide?: boolean }) {
  return (
    <li className={wide ? 'sm:col-span-2' : undefined}>
      <Link to={choice.to} className="group flex h-full items-start gap-4 rounded-2xl border border-line-strong bg-surface p-5 transition-[box-shadow,border-color] duration-200 hover:border-brand-300 hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-muted text-fg-muted transition-colors group-hover:border-brand-200 group-hover:bg-brand-50 group-hover:text-brand-600">
          <Plus className="size-[18px]" aria-hidden />
        </span>
        <span className="min-w-0">
          <h3 className="text-[17px] leading-snug font-semibold tracking-[-0.01em] text-fg group-hover:text-brand-700">{choice.name}</h3>
          <span className="mt-1 block text-sm leading-relaxed text-fg-muted">{choice.short}</span>
        </span>
      </Link>
    </li>
  )
}

const panel = 'rounded-2xl border border-line-strong bg-surface'
const label = 'text-[12px] font-semibold tracking-[0.1em] text-fg-muted uppercase'

/** The dashboard (owner, 2026-11-15, after the example they gave): a greeting with the date; "Continue writing" with
 *  the person's recent work; "Start something new"; and beside them their work in numbers with each section's list,
 *  and what can be done with their own paper. The left panel holds only the sections. Every card has a clear border. */
export function DashboardPage() {
  useTitle('Dashboard')
  const { user } = useAuth()
  const data = useData()
  const { items, error } = useYourWork()
  const choices = startChoices(data.config)
  const firstName = user?.displayName.split(' ')[0] ?? ''
  const all = items ?? []
  const recent = [...all].sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, 2) // two at most (owner, 2026-11-15); "See all" gives the total
  const writing = choices.filter((c) => c.group !== 'Your own paper')
  const ownPaper = choices.filter((c) => c.group === 'Your own paper')
  // each service its own list (owner, 2026-11-15), shown when the service is offered
  const lists = SECTION_LISTS.filter((l) => data.config.availability[l.service] && data.config.availability[l.service] !== 'soon')
  const count = (type: WorkItem['type']) => all.filter((i) => i.type === type).length
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })

  return (
    <div className="pb-10">
      <header className="animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both]">
        <h1 className="text-[2rem] leading-[1.1] font-semibold tracking-[-0.025em] text-fg sm:text-[2.6rem]">
          {greeting()}
          {firstName ? `, ${firstName}` : ''}
        </h1>
        <p className="mt-2 text-[15px] text-fg-muted">{today}</p>
      </header>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 space-y-8">
          <section aria-labelledby="continue" className={clsx(panel, 'animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] p-5 [animation-delay:80ms] sm:p-6')}>
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 id="continue" className={label}>Continue writing</h2>
              {all.length > 0 && <Link to="/app/work" className="text-[13px] font-medium text-brand-700 hover:underline">See all ({all.length})</Link>}
            </div>
            {items === null && !error ? (
              <Skeleton className="h-24 rounded-xl" />
            ) : recent.length ? (
              <ul className="-mx-2 divide-y divide-line">
                {recent.map((item) => <ContinueRow key={item.key} item={item} />)}
              </ul>
            ) : (
              <p className="rounded-xl border border-dashed border-line-strong px-4 py-7 text-center text-[15px] text-fg-muted">
                {error ? 'Your work could not be loaded just now.' : 'Nothing yet. Choose what you need below and PaperAid starts on it.'}
              </p>
            )}
          </section>

          <section aria-labelledby="sections" className="animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] [animation-delay:160ms]">
            <h2 id="sections" className={clsx(label, 'mb-3')}>Start something new</h2>
            <ul className="grid gap-4 sm:grid-cols-2">
              {writing.map((c, i) => <StartTile key={c.id} choice={c} wide={i === 0 && writing.length % 2 === 1} />)}
            </ul>
          </section>
        </div>

        <aside className="space-y-6 animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] [animation-delay:120ms]" aria-label="Your work at a glance">
          <section aria-labelledby="your-work" className={clsx(panel, 'p-5')}>
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="your-work" className={label}>Your work</h2>
              <Link to="/app/work" className="text-[13px] font-medium text-brand-700 hover:underline">Open</Link>
            </div>
            <dl className="mt-4 grid grid-cols-3 gap-2">
              {STANDING.map((s) => (
                <div key={s.label}>
                  <dt className="sr-only">{s.label}</dt>
                  <dd className="font-mono text-[1.9rem] leading-none font-semibold text-fg">{all.filter((i) => s.tones.includes(i.status.tone)).length}</dd>
                  <dd className="mt-1.5 text-[13px] text-fg-muted" aria-hidden>{s.label}</dd>
                </div>
              ))}
            </dl>
            <ul className="mt-5 space-y-0.5 border-t border-line pt-3">
              {lists.map((l) => {
                const Icon = KINDS[l.type].icon
                return (
                  <li key={l.type}>
                    <Link to={l.to} className="-mx-2 flex items-center gap-2.5 rounded-lg px-2 py-2 text-[15px] text-fg hover:bg-surface-subtle hover:text-brand-700">
                      <Icon className="size-[18px] shrink-0 text-fg-subtle" aria-hidden />
                      <span className="flex-1">{l.yours}{count(l.type) > 0 ? ` (${count(l.type)})` : ''}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </section>

          {ownPaper.length > 0 && (
            <section aria-labelledby="own-paper" className={clsx(panel, 'p-5')}>
              <div className="flex items-baseline justify-between gap-3">
                <h2 id="own-paper" className={label}>Your own paper</h2>
                <Link to={PAPERS} className="text-[13px] font-medium text-brand-700 hover:underline">History</Link>
              </div>
              <ul className="mt-3 space-y-0.5">
                {ownPaper.map((c) => (
                  <li key={c.id}>
                    <Link to={c.to} className="-mx-2 flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-surface-subtle">
                      <c.icon className="mt-0.5 size-[18px] shrink-0 text-fg-subtle" aria-hidden />
                      <span>
                        <span className="block text-[15px] text-fg">{c.action}</span>
                        <span className="block text-xs leading-relaxed text-fg-subtle">{c.short}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}

/** Everything the student has started, by section: what is still pending first, then what is done. */
export function YourWorkPage() {
  useTitle('Your work')
  const { items, error } = useYourWork()
  const [params] = useSearchParams()
  const only = params.get('section')
  const sections = SECTION_LISTS.filter((s) => !only || s.type === only)

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium tracking-tight text-fg sm:text-3xl">Your work</h1>
          <p className="mt-1 text-sm text-fg-muted">Everything you have started, by section. Open one to read, change or download it.</p>
        </div>
        <Link to="/app/history" className="text-sm font-semibold text-brand-700 hover:underline">
          Paper checks and formatting
        </Link>
      </div>
      {error && <Alert tone={items ? 'info' : 'danger'} className="mb-4">{items ? error : 'We could not load your work.'}</Alert>}
      {items === null && !error ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : items && items.length ? (
        <div className="space-y-8">
          {sections.map((section) => {
            const mine = items.filter((i) => i.type === section.type)
            if (!mine.length) return null
            const pending = mine.filter((i) => !i.done)
            const done = mine.filter((i) => i.done)
            return (
              <section key={section.type} aria-labelledby={`work-${section.type}`}>
                <div className="mb-2 flex items-center justify-between">
                  <h2 id={`work-${section.type}`} className="text-[15px] font-medium text-fg">{section.label}</h2>
                  <Link to={section.to} className="text-sm font-medium text-brand-700 hover:underline">Open {section.label.toLowerCase()}</Link>
                </div>
                {pending.length > 0 && (
                  <>
                    <p className="mb-1.5 text-xs font-semibold tracking-[0.06em] text-fg-subtle uppercase">Pending ({pending.length})</p>
                    <ItemList items={pending} />
                  </>
                )}
                {done.length > 0 && (
                  <>
                    <p className={`mb-1.5 text-xs font-semibold tracking-[0.06em] text-fg-subtle uppercase ${pending.length ? 'mt-4' : ''}`}>Done ({done.length})</p>
                    <ItemList items={done} />
                  </>
                )}
              </section>
            )
          })}
          {only && <Link to="/app/work" className="inline-block text-sm font-medium text-brand-700 hover:underline">See all your work</Link>}
        </div>
      ) : (
        <EmptyState icon={<FolderOpen className="size-5" />} title="Nothing here yet" action={<ButtonLink to="/app">See what you can start</ButtonLink>}>
          Your coursework, proposals and funding documents will be listed here.
        </EmptyState>
      )}
    </>
  )
}
