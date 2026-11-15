import { FilePen, HandCoins, Lightbulb, NotebookPen, ScrollText } from 'lucide-react'
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useData } from '../../lib/data'
import { createRefresher, startPolling } from '../../lib/refresher'
import type { StartChoice } from '../../lib/start'
import type { ServiceId, WorkSummary } from '../../lib/types'
import type { WorkspaceStatus } from '../workspace/parts'

/** One piece of the student's work: a coursework, funding document or proposal, with one plain status. */
export interface WorkItem {
  key: string
  title: string
  kind: string
  /** Which of the person's services it belongs to (each its own section since 2026-11-15). */
  type: WorkSummary['kind']
  icon: typeof NotebookPen
  status: WorkspaceStatus
  updated: string
  to: string
  /** The section it belongs to, as the dashboard and the left panel name them. */
  group: StartChoice['group']
  /** False while it is being written, waits for the student or has nothing to read yet. */
  done: boolean
}

/** Each service's own list, in the owner's order (2026-11-15: coursework, research concept notes, research proposals,
 *  funding concept notes, funding proposals; each its own section, never mixed). `service` is whose availability
 *  decides whether it is shown. */
export const SECTION_LISTS: { type: WorkSummary['kind']; label: string; yours: string; to: string; service: ServiceId }[] = [
  { type: 'COURSEWORK', label: 'Coursework', yours: 'Your coursework', to: '/app/works?section=COURSEWORK', service: 'COURSEWORK' },
  { type: 'RESEARCH_CONCEPT', label: 'Research concept notes', yours: 'Your research concept notes', to: '/app/projects?goal=CONCEPT', service: 'PROPOSAL' },
  { type: 'PROPOSAL', label: 'Research proposals', yours: 'Your research proposals', to: '/app/projects', service: 'PROPOSAL' },
  { type: 'CONCEPT_NOTE', label: 'Funding concept notes', yours: 'Your funding concept notes', to: '/app/works?section=CONCEPT_NOTE', service: 'CONCEPT_NOTE' },
  { type: 'FUNDING_PROPOSAL', label: 'Funding proposals', yours: 'Your funding proposals', to: '/app/works?section=FUNDING_PROPOSAL', service: 'FUNDING_PROPOSAL' },
]

export const KINDS: Record<WorkSummary['kind'], { label: string; icon: typeof NotebookPen; path: string }> = {
  COURSEWORK: { label: 'Coursework', icon: NotebookPen, path: '/app/works' },
  RESEARCH_CONCEPT: { label: 'Research concept note', icon: Lightbulb, path: '/app/projects' },
  PROPOSAL: { label: 'Research proposal', icon: FilePen, path: '/app/projects' },
  CONCEPT_NOTE: { label: 'Funding concept note', icon: ScrollText, path: '/app/works' },
  FUNDING_PROPOSAL: { label: 'Funding proposal', icon: HandCoins, path: '/app/works' },
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
    default: return { label: 'Not started', tone: 'idle' }
  }
}

function item(s: WorkSummary): WorkItem {
  const kind = KINDS[s.kind]
  return {
    key: s.id, title: s.title, kind: kind.label, type: s.kind, icon: kind.icon, updated: s.updatedAt, to: `${kind.path}/${s.id}`, status: status(s), group: s.section,
    done: ['READY', 'READY_WITH_WARNINGS', 'CHAPTERS', 'CONCEPT'].includes(s.state),
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
