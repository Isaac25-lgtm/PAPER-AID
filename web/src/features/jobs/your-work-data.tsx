import { ChartColumn, FilePen, HandCoins, Lightbulb, NotebookPen } from 'lucide-react'
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useData } from '../../lib/data'
import { createRefresher, startPolling } from '../../lib/refresher'
import type { StartChoice } from '../../lib/start'
import type { WorkSummary } from '../../lib/types'
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

const KINDS: Record<WorkSummary['kind'], { label: string; icon: typeof NotebookPen; path: string }> = {
  COURSEWORK: { label: 'Coursework', icon: NotebookPen, path: '/app/works' },
  CONCEPT_NOTE: { label: 'Concept note', icon: Lightbulb, path: '/app/works' },
  FUNDING_PROPOSAL: { label: 'Funding proposal', icon: HandCoins, path: '/app/works' },
  PROPOSAL: { label: 'Research proposal', icon: FilePen, path: '/app/projects' },
  DATALAB: { label: 'Data Lab', icon: ChartColumn, path: '/app/datalab' },
}

function status(s: WorkSummary): WorkspaceStatus {
  switch (s.state) {
    case 'WRITING': return { label: 'Writing…', tone: 'running' }
    case 'FAILED': return { label: "Couldn't finish · not charged", tone: 'danger' }
    case 'READY': return { label: 'Ready', tone: 'ready' }
    case 'READY_WITH_WARNINGS': return { label: 'Ready with warnings', tone: 'warn' }
    case 'NEEDS_ATTENTION': return { label: 'Needs your attention', tone: 'input' }
    case 'CHAPTERS': return { label: s.chapters.length === 3 ? 'Chapters 1–3 written' : `Chapter ${s.chapters.join(', ')} written`, tone: 'ready' }
    case 'CONCEPT': return { label: 'Concept paper written', tone: 'ready' }
    case 'REPORT': return { label: 'Report ready', tone: 'ready' }
    case 'ANALYSES': return { label: `${s.analyses} analys${s.analyses === 1 ? 'is' : 'es'}`, tone: 'idle' }
    case 'NOT_ANALYSED': return { label: 'Not analysed yet', tone: 'idle' }
    case 'NO_DATA': return { label: 'No data yet', tone: 'idle' }
    default: return { label: 'Not started', tone: 'idle' }
  }
}

function item(s: WorkSummary): WorkItem {
  const kind = KINDS[s.kind]
  return {
    key: s.id, title: s.title, kind: kind.label, icon: kind.icon, updated: s.updatedAt, to: `${kind.path}/${s.id}`, status: status(s), group: s.section,
    done: ['READY', 'READY_WITH_WARNINGS', 'CHAPTERS', 'CONCEPT', 'REPORT'].includes(s.state),
  }
}

interface YourWork {
  items: WorkItem[] | null
  /** The list could not be loaded, or (with `items`) could not be refreshed: what is shown is what was last loaded. */
  error: string | null
}

const Context = createContext<YourWork>({ items: null, error: null })

const WHILE_WRITING = 15_000 // something is being written: it turns to Ready by itself
const OTHERWISE = 60_000

/** Loads the person's work once for the whole app shell (the left panel and the pages share it) and keeps it fresh:
 *  one light request at a time, the last good list kept when a refresh fails, nothing asked while the tab is hidden
 *  (Codex's audit of cbb99cb, findings 7 to 9). */
export function YourWorkProvider({ children }: { children: ReactNode }) {
  const data = useData()
  const [items, setItems] = useState<WorkItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const writing = useRef(false)

  useEffect(() => {
    const refresher = createRefresher(
      () => data.yourWork(),
      (list) => {
        writing.current = list.some((s) => s.state === 'WRITING')
        setItems(list.map(item))
      },
      (failed) => setError(failed ? 'We could not refresh your work just now. This is what was last loaded.' : null),
    )
    const stop = startPolling(() => refresher.refresh(), () => (writing.current ? WHILE_WRITING : OTHERWISE), () => document.hidden)
    const shown = () => {
      if (!document.hidden) void refresher.refresh()
    }
    document.addEventListener('visibilitychange', shown)
    return () => {
      refresher.stop()
      stop()
      document.removeEventListener('visibilitychange', shown)
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
