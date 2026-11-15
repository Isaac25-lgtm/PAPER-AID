import { clsx } from 'clsx'
import { ArrowRight, Check, FolderOpen, Loader2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Alert, Card, EmptyState, Skeleton } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { startChoices, type StartChoice } from '../../lib/start'
import { useTitle } from '../../lib/use-title'
import { useAuth } from '../auth/auth-context'
import { StatusChip } from '../workspace/parts'
import { SECTION_LISTS, useYourWork, type WorkItem } from './your-work-data'

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
const GROUP_LIST: Record<StartChoice['group'], { to: string; label: string }> = {
  'Coursework': { to: '/app/works', label: 'Your coursework' },
  'Research proposals': { to: '/app/projects', label: 'Your proposals' },
  'Funding': { to: '/app/works?section=FUNDING', label: 'Your funding documents' },
  'Your own paper': { to: '/app/history', label: 'Your papers' },
}

/** A small page, drawn as a document thumbnail: decoration only, never content. */
function PagePreview({ seed, large = false }: { seed: number; large?: boolean }) {
  const widths = [92, 84, 96, 70, 88, 78, 94, 62, 86, 74]
  const lines = Array.from({ length: large ? 9 : 5 }, (_, i) => widths[(i + seed * 3) % widths.length])
  return (
    <div aria-hidden className={clsx('rounded-t-md border border-b-0 border-line bg-white shadow-[0_8px_24px_-12px_rgb(16_24_40/0.18)] transition-transform duration-500 ease-[cubic-bezier(.2,.8,.3,1)] group-hover:-translate-y-1',
      large ? 'w-[62%] px-5 pt-5' : 'w-[64%] px-3.5 pt-3.5')}>
      <div className={clsx('rounded-full bg-brand-200', large ? 'mb-4 h-2.5 w-1/2' : 'mb-2.5 h-1.5 w-2/5')} />
      <div className={large ? 'space-y-2.5' : 'space-y-1.5'}>
        {lines.map((w, i) => <div key={i} className={clsx('rounded-full bg-surface-muted', large ? 'h-1.5' : 'h-1')} style={{ width: `${w}%` }} />)}
      </div>
    </div>
  )
}

/** One thing that can be started, as a document card: its page on a soft panel, then what it is. */
function StartCard({ choice, seed }: { choice: StartChoice; seed: number }) {
  return (
    <li>
      <Link to={choice.to} className="group flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-white transition-[box-shadow,border-color,translate] duration-300 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
        <div className="relative hidden h-28 items-end justify-center bg-gradient-to-b from-brand-50 to-surface-subtle sm:flex">
          <span className="absolute top-3 left-3 flex size-8 items-center justify-center rounded-lg border border-line bg-white text-brand-600 shadow-card">
            <choice.icon className="size-4" aria-hidden />
          </span>
          <PagePreview seed={seed} />
        </div>
        <div className="flex flex-1 flex-col p-4 sm:border-t sm:border-line">
          <span className="mb-2.5 flex size-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600 sm:hidden">
            <choice.icon className="size-4" aria-hidden />
          </span>
          <span className="text-[11px] font-medium tracking-[0.06em] text-fg-subtle uppercase">{choice.group}</span>
          <span className="mt-1 text-[15px] font-medium text-fg group-hover:text-brand-700">{choice.name}</span>
          <span className="mt-1 flex-1 text-[13px] leading-relaxed text-fg-subtle">{choice.short}</span>
          <span className="mt-3 flex items-center gap-1 text-[13px] font-medium text-brand-700">
            {choice.action} <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </span>
        </div>
      </Link>
    </li>
  )
}

/** One piece of recent work as a document card (owner, 2026-11-15: the dashboard looks like Jenni's): its page with
 *  its title on it, then what it is, when it changed and where it stands. */
function RecentCard({ item }: { item: WorkItem }) {
  return (
    <li>
      <Link to={item.to} className="group flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-white transition-[box-shadow,border-color,translate] duration-300 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
        <div className="flex h-36 items-end justify-center bg-surface-subtle px-6 pt-5">
          <div aria-hidden className="h-full w-full rounded-t-md border border-b-0 border-line bg-white px-4 pt-4 shadow-[0_8px_24px_-12px_rgb(16_24_40/0.18)] transition-transform duration-500 ease-[cubic-bezier(.2,.8,.3,1)] group-hover:-translate-y-1">
            <p className="line-clamp-2 font-serif text-[11px] leading-snug font-semibold text-fg">{item.title}</p>
            <div className="mt-2.5 space-y-1.5">
              {[94, 86, 90, 72].map((w, i) => <div key={i} className="h-1 rounded-full bg-surface-muted" style={{ width: `${w}%` }} />)}
            </div>
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-2 border-t border-line p-4">
          <p className="truncate text-[15px] font-medium text-fg group-hover:text-brand-700">{item.title}</p>
          <p className="flex items-center gap-1.5 truncate text-xs text-fg-subtle">
            <item.icon className="size-3.5 shrink-0" aria-hidden />
            {item.kind} · {new Date(item.updated).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
          </p>
          <div className="mt-auto pt-1"><StatusChip status={item.status} /></div>
        </div>
      </Link>
    </li>
  )
}

/** The first choice (coursework, the flagship), wide: what it gives, its button, and a larger page. */
function FeaturedCard({ choice }: { choice: StartChoice }) {
  return (
    <Link to={choice.to} className="group grid overflow-hidden rounded-2xl border border-line bg-white transition-[box-shadow,border-color] duration-300 hover:border-brand-200 hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 md:grid-cols-[1.15fr_1fr]">
      <div className="flex flex-col p-6 sm:p-7">
        <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <choice.icon className="size-5" aria-hidden />
        </span>
        <span className="mt-4 text-xl font-medium tracking-[-0.01em] text-fg">{choice.name}</span>
        <span className="mt-1.5 text-[15px] leading-relaxed text-fg-muted">{choice.short}</span>
        <ul className="mt-4 space-y-1.5">
          {choice.benefits.map((b) => (
            <li key={b} className="flex items-center gap-2 text-[13px] text-fg-muted"><Check className="size-3.5 shrink-0 text-brand-600" aria-hidden /> {b}</li>
          ))}
        </ul>
        <span className="mt-6 inline-flex h-9 w-fit items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] transition-colors group-hover:bg-brand-700">
          {choice.action} <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </div>
      <div className="hidden items-end justify-center bg-gradient-to-br from-brand-50 via-brand-50/60 to-surface-subtle pt-8 md:flex">
        <PagePreview seed={0} large />
      </div>
    </Link>
  )
}

/** The dashboard (owner, 2026-11-15, replacing the rule of 2026-10-10: it looks like Jenni's): a greeting, coursework
 *  first, the person's recent work as document cards, then everything else they can start. */
export function DashboardPage() {
  useTitle('Dashboard')
  const { user } = useAuth()
  const data = useData()
  const { items } = useYourWork()
  const choices = startChoices(data.config)
  const groups = [...new Set(choices.map((c) => c.group))]
  const firstName = user?.displayName.split(' ')[0] ?? ''
  const running = (items ?? []).filter((i) => i.status.tone === 'running')
  const featured = choices.find((c) => c.group === 'Coursework') ?? choices[0]
  const others = choices.filter((c) => c !== featured)
  const count = (group: string) => (items ?? []).filter((i) => i.group === group).length
  const recent = [...(items ?? [])].sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, 6)

  return (
    <div className="mx-auto max-w-[60rem] pb-10 sm:pt-6">
      <div className="animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] text-center">
        <p className="text-sm text-fg-subtle">
          {greeting()}
          {firstName ? `, ${firstName}` : ''}
        </p>
        <h1 className="mt-2 text-[1.9rem] leading-[1.15] font-medium tracking-[-0.03em] text-fg sm:text-[2.6rem]">What are you working on today?</h1>
        <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-fg-muted">
          Choose what you need. PaperAid researches, writes and checks it, and you download the finished document.
        </p>
      </div>

      {running.length > 0 && (
        <Link to={running.length === 1 ? running[0].to : '/app/work'}
          className="mx-auto mt-6 flex max-w-xl items-center gap-2.5 rounded-full border border-brand-200 bg-brand-50 px-4 py-2 text-sm text-brand-800 hover:border-brand-300 focus-visible:outline-2 focus-visible:outline-brand-600">
          <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
          <span className="min-w-0 flex-1 truncate">
            {running.length === 1 ? <>PaperAid is writing <span className="font-medium">{running[0].title}</span></> : `PaperAid is writing ${running.length} pieces of your work`}
          </span>
          <span className="shrink-0 font-medium">Open</span>
        </Link>
      )}

      <section aria-labelledby="sections" className="mt-10">
        <h2 id="sections" className="sr-only">What you can do</h2>
        {featured && (
          <div className="animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] [animation-delay:120ms]">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h3 className="text-[12px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">{featured.group}</h3>
              <Link to={GROUP_LIST[featured.group].to} className="text-[13px] font-medium text-brand-700 hover:underline">
                {GROUP_LIST[featured.group].label}
                {count(featured.group) > 0 ? ` (${count(featured.group)})` : ''}
              </Link>
            </div>
            <FeaturedCard choice={featured} />
          </div>
        )}
        {recent.length > 0 && (
          <div className="mt-10 animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] [animation-delay:180ms]">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h3 className="text-[12px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Recent work</h3>
              <Link to="/app/work" className="text-[13px] font-medium text-brand-700 hover:underline">See all</Link>
            </div>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {recent.map((item) => <RecentCard key={item.key} item={item} />)}
            </ul>
          </div>
        )}
        {others.length > 0 && (
          <div className="mt-10 animate-[rise_.6s_cubic-bezier(.2,.8,.3,1)_both] [animation-delay:220ms]">
            <h3 className="mb-3 text-[12px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">More you can start</h3>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {others.map((c, i) => <StartCard key={c.id} choice={c} seed={i + 1} />)}
            </ul>
          </div>
        )}
        <nav aria-label="Your work" className="mt-10 flex flex-wrap items-center justify-center gap-2 border-t border-line pt-6">
          <span className="mr-1 text-[13px] text-fg-subtle">Your work:</span>
          {groups.filter((g) => g !== featured?.group).map((g) => (
            <Link key={g} to={GROUP_LIST[g].to} className="rounded-full border border-line bg-white px-3 py-1 text-[13px] font-medium text-fg-muted transition-colors hover:border-brand-200 hover:text-brand-700">
              {GROUP_LIST[g].label}
              {count(g) > 0 ? ` (${count(g)})` : ''}
            </Link>
          ))}
        </nav>
      </section>
    </div>
  )
}

/** Everything the student has started, by section: what is still pending first, then what is done. */
export function YourWorkPage() {
  useTitle('Your work')
  const { items, error } = useYourWork()
  const [params] = useSearchParams()
  const only = params.get('section')
  const sections = SECTION_LISTS.filter((s) => !only || s.group === only)

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
            const mine = items.filter((i) => i.group === section.group)
            if (!mine.length) return null
            const pending = mine.filter((i) => !i.done)
            const done = mine.filter((i) => i.done)
            return (
              <section key={section.group} aria-labelledby={`work-${section.label}`}>
                <div className="mb-2 flex items-center justify-between">
                  <h2 id={`work-${section.label}`} className="text-[15px] font-medium text-fg">{section.label}</h2>
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
