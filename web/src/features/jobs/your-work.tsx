import { ArrowRight, FilePen, FolderOpen, HandCoins, Lightbulb, NotebookPen } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ButtonLink } from '../../components/ui/button'
import { Alert, Card, EmptyState, Skeleton } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { formatTokenNumber } from '../../lib/format'
import type { Project } from '../../lib/proposal-types'
import { startChoices } from '../../lib/start'
import type { Job } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useWallet } from '../../lib/use-wallet'
import type { Work } from '../../lib/work-types'
import { useAuth } from '../auth/auth-context'
import { KIND_LABELS } from '../works/shared'
import { StatusChip, type WorkspaceStatus } from '../workspace/parts'
import { useJobList } from './hooks'
import { JobRow } from './job-bits'

/** One row of "Your work": a coursework, funding document or proposal, with one plain status. */
interface Item {
  key: string
  title: string
  kind: string
  icon: typeof NotebookPen
  status: WorkspaceStatus
  updated: string
  to: string
}

function workItem(w: Work): Item {
  const status: WorkspaceStatus = w.activeJob
    ? { label: 'Writing…', tone: 'running' }
    : w.autoFailure && !w.documents.length
      ? { label: "Couldn't finish · not charged", tone: 'danger' }
      : w.documents.length
        ? w.status === 'READY'
          ? { label: 'Ready', tone: 'ready' }
          : w.status === 'READY_WITH_WARNINGS'
            ? { label: 'Ready with warnings', tone: 'warn' }
            : w.readiness.some((i) => i.basis === 'AUTHOR' && !['PASS', 'NOT_APPLICABLE'].includes(i.status))
              ? { label: 'Needs your input', tone: 'input' }
              : { label: 'Check before you submit', tone: 'danger' }
        : { label: 'Not started', tone: 'idle' }
  return {
    key: w.id, title: w.plan?.title ?? w.inputs.title, kind: KIND_LABELS[w.kind], updated: w.updatedAt, to: `/app/works/${w.id}`,
    icon: w.kind === 'COURSEWORK' ? NotebookPen : w.kind === 'CONCEPT_NOTE' ? Lightbulb : HandCoins, status,
  }
}

function projectItem(p: Project): Item {
  const written = p.chapters.filter((c) => c.current && c.number !== 4).map((c) => c.number)
  const concept = p.chapters.some((c) => c.number === 4 && c.current)
  const status: WorkspaceStatus = p.activeJob
    ? { label: 'Writing…', tone: 'running' }
    : p.autoFailure && !written.length && !concept
      ? { label: "Couldn't finish · not charged", tone: 'danger' }
      : written.length
        ? { label: written.length === 3 ? 'Chapters 1–3 written' : `Chapter ${written.join(', ')} written`, tone: 'ready' }
        : concept
          ? { label: 'Concept paper written', tone: 'ready' }
          : { label: 'Not started', tone: 'idle' }
  return { key: p.id, title: p.plan?.title ?? p.inputs.topic, kind: 'Research proposal', icon: FilePen, updated: p.updatedAt, to: `/app/projects/${p.id}`, status }
}

function useYourWork() {
  const data = useData()
  const [items, setItems] = useState<Item[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      Promise.all([data.works.list().catch(() => [] as Work[]), data.projects.list().catch(() => [] as Project[])])
        .then(([works, projects]) => {
          if (!alive) return
          setItems([...works.map(workItem), ...projects.map(projectItem)].sort((a, b) => b.updated.localeCompare(a.updated)))
        })
        .catch((e: unknown) => alive && setError(e instanceof DataError ? e.message : 'We could not load your work.'))
    load()
    const timer = window.setInterval(load, 15000) // a running item changes to Ready by itself
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [data])
  return { items, error }
}

function ItemRow({ item }: { item: Item }) {
  return (
    <li>
      <Link to={item.to} className="group flex items-center gap-4 rounded-xl px-3 py-3.5 transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-brand-600 sm:px-4">
        <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
          <item.icon className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-fg group-hover:text-brand-800">{item.title}</p>
          <p className="mt-0.5 truncate text-xs text-fg-subtle">
            {item.kind} · {new Date(item.updated).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <StatusChip status={item.status} />
      </Link>
    </li>
  )
}

function ItemList({ items, limit }: { items: Item[]; limit?: number }) {
  return (
    <Card className="p-1.5">
      <ul className="divide-y divide-line">
        {(limit ? items.slice(0, limit) : items).map((item) => (
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

/** The dashboard (owner decision 2026-10-01): the student's work first, starting something new second. */
export function DashboardPage() {
  useTitle('Dashboard')
  const { user } = useAuth()
  const data = useData()
  const { wallet } = useWallet()
  const { items, error } = useYourWork()
  const papers = useJobList({ limit: 4 })
  const paperJobs = papers.jobs.filter((j: Job) => !j.projectId && !j.services.some((s) => ['COURSEWORK', 'CONCEPT_NOTE', 'FUNDING_PROPOSAL', 'PROPOSAL'].includes(s)))
  const choices = startChoices(data.config)
  const firstName = user?.displayName.split(' ')[0] ?? ''

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">
            {greeting()}
            {firstName ? `, ${firstName}` : ''}
          </h1>
          <p className="mt-1 text-sm text-fg-muted">Pick up your work, or start something new.</p>
        </div>
        {data.config.creditsEnabled && wallet && (
          <Link to="/app/credits" className="rounded-xl border border-line bg-white px-4 py-2.5 text-sm shadow-card hover:border-brand-300">
            <span className="text-fg-muted">Your credits </span>
            <span className="font-bold text-fg">{formatTokenNumber(wallet.available)}</span>
            {wallet.held > 0 && <span className="text-xs text-fg-muted"> · {formatTokenNumber(wallet.held)} reserved</span>}
          </Link>
        )}
      </div>

      <section aria-labelledby="your-work" className="mb-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="your-work" className="text-lg font-semibold">
            Your work
          </h2>
          {items && items.length > 6 && (
            <Link to="/app/work" className="text-sm font-semibold text-brand-700 hover:underline">
              See all
            </Link>
          )}
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        {items === null && !error ? (
          <Skeleton className="h-40 rounded-2xl" />
        ) : items && items.length ? (
          <ItemList items={items} limit={6} />
        ) : (
          <EmptyState icon={<FolderOpen className="size-5" />} title="Nothing here yet" action={choices[0] && <ButtonLink to={choices[0].to}>{choices[0].action}</ButtonLink>}>
            Start your first piece of work. It will appear here, with its status, whenever you come back.
          </EmptyState>
        )}
      </section>

      <section aria-labelledby="start-new">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="start-new" className="text-lg font-semibold">
            Start something new
          </h2>
          <Link to="/app/new" className="text-sm font-semibold text-brand-700 hover:underline">
            Every service
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {choices.slice(0, 4).map((c) => (
            <Link key={c.id} to={c.to}
              className="group flex flex-col rounded-2xl border border-line-strong/60 bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:border-brand-400 focus-visible:outline-2 focus-visible:outline-brand-600">
              <span className="grid size-9 place-items-center rounded-lg bg-brand-50 text-brand-700">
                <c.icon className="size-5" aria-hidden />
              </span>
              <span className="mt-3 text-sm font-semibold text-fg">{c.name}</span>
              <span className="mt-1 flex-1 text-xs text-fg-muted">{c.short}</span>
              <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-700">
                {c.action} <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            </Link>
          ))}
        </div>
      </section>

      {paperJobs.length > 0 && (
        <section aria-labelledby="papers" className="mt-10">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="papers" className="text-lg font-semibold">
              Paper checks and formatting
            </h2>
            <Link to="/app/history" className="text-sm font-semibold text-brand-700 hover:underline">
              See all
            </Link>
          </div>
          <Card className="p-1.5">
            <ul className="divide-y divide-line">
              {paperJobs.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </ul>
          </Card>
        </section>
      )}
    </>
  )
}

/** Everything the student has written with PaperAid, newest first; paper checks keep their history. */
export function YourWorkPage() {
  useTitle('Your work')
  const { items, error } = useYourWork()
  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">Your work</h1>
          <p className="mt-1 text-sm text-fg-muted">Everything you have started, with where it is. Open one to read, change or download it.</p>
        </div>
        <Link to="/app/history" className="text-sm font-semibold text-brand-700 hover:underline">
          Paper checks and formatting
        </Link>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {items === null && !error ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : items && items.length ? (
        <ItemList items={items} />
      ) : (
        <EmptyState icon={<FolderOpen className="size-5" />} title="Nothing here yet" action={<ButtonLink to="/app/new">Start something</ButtonLink>}>
          Your coursework, proposals and funding documents will be listed here.
        </EmptyState>
      )}
    </>
  )
}
