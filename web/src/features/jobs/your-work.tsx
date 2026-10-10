import { ArrowRight, FolderOpen, Loader2 } from 'lucide-react'
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
  'Data analysis': { to: '/app/datalab', label: 'Your data projects' },
  'Your own paper': { to: '/app/history', label: 'Your papers' },
}

/** The dashboard (owner, 2026-10-10): what a person can start, by section, and nothing else. Their own work is in
 *  the left panel and under each section, so the page never fills up with it; one line says when something is
 *  being written. */
export function DashboardPage() {
  useTitle('Dashboard')
  const { user } = useAuth()
  const data = useData()
  const { items } = useYourWork()
  const choices = startChoices(data.config)
  const groups = [...new Set(choices.map((c) => c.group))]
  const firstName = user?.displayName.split(' ')[0] ?? ''
  const running = (items ?? []).filter((i) => i.status.tone === 'running')

  return (
    <>
      <h1 className="text-2xl font-medium tracking-tight text-fg sm:text-[28px]">
        {greeting()}
        {firstName ? `, ${firstName}` : ''}
      </h1>
      <p className="mt-1 text-[15px] text-fg-muted">What would you like to do?</p>

      {running.length > 0 && (
        <Link to={running.length === 1 ? running[0].to : '/app/work'}
          className="mt-5 flex items-center gap-2.5 rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm text-brand-800 hover:border-brand-300 focus-visible:outline-2 focus-visible:outline-brand-600">
          <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
          <span className="min-w-0 flex-1 truncate">
            {running.length === 1 ? <>PaperAid is writing <span className="font-medium">{running[0].title}</span></> : `PaperAid is writing ${running.length} pieces of your work`}
          </span>
          <span className="shrink-0 font-medium">Open</span>
        </Link>
      )}

      <section aria-labelledby="sections" className="mt-6">
        <h2 id="sections" className="sr-only">What you can do</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) => {
            const mine = (items ?? []).filter((i) => i.group === group).length
            return (
              <Card key={group} className="flex flex-col p-2">
                <h3 className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">{group}</h3>
                <ul className="flex-1">
                  {choices.filter((c) => c.group === group).map((c) => (
                    <li key={c.id}>
                      <Link to={c.to} className="group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-brand-600">
                        <c.icon className="mt-0.5 size-[18px] shrink-0 text-brand-600" aria-hidden />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-fg group-hover:text-brand-700">{c.name}</span>
                          <span className="mt-0.5 block text-xs text-fg-subtle">{c.short}</span>
                        </span>
                        <ArrowRight className="mt-1 size-3.5 shrink-0 text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ul>
                <Link to={GROUP_LIST[group].to} className="mx-3 mt-1 mb-1.5 border-t border-line pt-2.5 text-[13px] font-medium text-brand-700 hover:underline">
                  {GROUP_LIST[group].label}
                  {mine > 0 ? ` (${mine})` : ''}
                </Link>
              </Card>
            )
          })}
        </div>
      </section>
    </>
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
