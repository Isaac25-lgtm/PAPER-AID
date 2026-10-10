import { ChartColumn, FilePen, HandCoins, Lightbulb, NotebookPen } from 'lucide-react'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { DataError, useData } from '../../lib/data'
import type { DataProject } from '../../lib/datalab-types'
import type { Project } from '../../lib/proposal-types'
import type { StartChoice } from '../../lib/start'
import type { Work } from '../../lib/work-types'
import { KIND_LABELS } from '../works/shared'
import type { WorkspaceStatus } from '../workspace/parts'

/** One piece of the student's work: a coursework, funding document, proposal or dataset, with one plain status. */
export interface WorkItem {
  key: string
  title: string
  kind: string
  icon: typeof NotebookPen
  status: WorkspaceStatus
  updated: string
  to: string
  /** The section it belongs to, as the dashboard and the left panel name them. */
  group: StartChoice['group']
  /** False while it is being written, waits for the student or has nothing to read yet. */
  done: boolean
}

/** Where each section keeps its own list (owner, 2026-10-10: the work lives in the left panel, by section). */
export const SECTION_LISTS: { group: StartChoice['group']; label: string; to: string }[] = [
  { group: 'Coursework', label: 'Coursework', to: '/app/works' },
  { group: 'Research proposals', label: 'Research proposals', to: '/app/projects' },
  { group: 'Funding', label: 'Funding', to: '/app/works?section=FUNDING' },
  { group: 'Data analysis', label: 'Data Lab', to: '/app/datalab' },
]

function workItem(w: Work): WorkItem {
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
    group: w.kind === 'COURSEWORK' ? 'Coursework' : 'Funding', done: !w.activeJob && w.documents.length > 0 && status.tone !== 'input',
  }
}

function projectItem(p: Project): WorkItem {
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
  return {
    key: p.id, title: p.plan?.title ?? p.inputs.topic, kind: 'Research proposal', icon: FilePen, updated: p.updatedAt, to: `/app/projects/${p.id}`, status,
    group: 'Research proposals', done: !p.activeJob && (written.length > 0 || concept),
  }
}

function dataItem(p: DataProject): WorkItem {
  const status: WorkspaceStatus = p.activeJob
    ? { label: 'Writing…', tone: 'running' }
    : p.reports.length
      ? { label: 'Report ready', tone: 'ready' }
      : p.pending.length || p.survey === 'ASK'
        ? { label: 'Needs your input', tone: 'input' }
        : p.analyses.length
          ? { label: `${p.analyses.length} analys${p.analyses.length === 1 ? 'is' : 'es'}`, tone: 'idle' }
          : { label: p.source ? 'Not analysed yet' : 'No data yet', tone: 'idle' }
  return {
    key: p.id, title: p.title, kind: 'Data Lab', icon: ChartColumn, updated: p.updatedAt, to: `/app/datalab/${p.id}`, status,
    group: 'Data analysis', done: !p.activeJob && p.reports.length > 0,
  }
}

interface YourWork {
  items: WorkItem[] | null
  error: string | null
}

const Context = createContext<YourWork>({ items: null, error: null })

/** Loads the student's work once for the whole app shell (the left panel and the pages share it) and keeps it fresh. */
export function YourWorkProvider({ children }: { children: ReactNode }) {
  const data = useData()
  const [items, setItems] = useState<WorkItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      Promise.all([data.works.list().catch(() => [] as Work[]), data.projects.list().catch(() => [] as Project[]), data.datalab.list().catch(() => [] as DataProject[])])
        .then(([works, projects, datasets]) => {
          if (!alive) return
          setItems([...works.map(workItem), ...projects.map(projectItem), ...datasets.map(dataItem)].sort((a, b) => b.updated.localeCompare(a.updated)))
        })
        .catch((e: unknown) => alive && setError(e instanceof DataError ? e.message : 'We could not load your work.'))
    load()
    const timer = window.setInterval(load, 15000) // a running item changes to Ready by itself
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [data])
  return <Context.Provider value={{ items, error }}>{children}</Context.Provider>
}

export function useYourWork(): YourWork {
  return useContext(Context)
}

/** Pending work first (newest first), then what is done. */
export function pendingFirst(items: WorkItem[]): WorkItem[] {
  return [...items.filter((i) => !i.done), ...items.filter((i) => i.done)]
}
