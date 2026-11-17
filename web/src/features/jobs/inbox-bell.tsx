import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import { AlertTriangle, Bell, CheckCircle2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useData, type Inbox } from '../../lib/data'
import { createRefresher, startPolling, type Refresher } from '../../lib/refresher'

const EVERY = 90_000 // a light request while the tab is visible; email and text messages remain the prompt

function when(at: string) {
  const minutes = Math.round((Date.now() - new Date(at).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`
  return new Date(at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export interface InboxState {
  inbox: Inbox | null
  /** The bell was opened: everything shown is read. */
  markRead: () => void
}

/** The person's in-app notifications, loaded once for the app shell and refreshed while the tab is visible. */
export function useInbox(): InboxState {
  const data = useData()
  const [inbox, setInbox] = useState<Inbox | null>(null)
  const refresher = useRef<Refresher | null>(null)

  useEffect(() => {
    const r = createRefresher(() => data.inbox(), setInbox, () => undefined) // a failed refresh keeps what was shown
    refresher.current = r
    const stop = startPolling(() => r.refresh(), () => EVERY, () => document.hidden)
    return () => {
      r.stop()
      stop()
    }
  }, [data])

  const markRead = () => {
    if (!inbox?.unread) return
    setInbox({ unread: 0, items: inbox.items.map((i) => ({ ...i, unread: false })) })
    data.readInbox().catch(() => void refresher.current?.refresh()) // not recorded: the next refresh shows them unread again
  }
  return { inbox, markRead }
}

/** In-app notifications (owner, 2026-11-17, after PaperAid Pro): a bell with what is unread; opening it lists the
 *  latest work that is ready or stopped and marks it read. The same messages as email and text, never content. */
export function InboxBell({ state, align = 'start' }: { state: InboxState; align?: 'start' | 'end' }) {
  const { inbox, markRead } = state
  const unread = inbox?.unread ?? 0
  return (
    <Menu.Root onOpenChange={(open) => open && markRead()}>
      <Menu.Trigger aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        className="relative grid size-9 place-items-center rounded-lg text-fg-muted transition-colors hover:bg-surface-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand-600">
        <Bell className="size-[18px]" aria-hidden />
        {unread > 0 && (
          <span className="absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-brand-600 px-1 text-[10px] leading-4 font-semibold text-white">{unread > 9 ? '9+' : unread}</span>
        )}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align={align} sideOffset={8} className="z-50 max-h-[min(70vh,32rem)] w-80 overflow-y-auto rounded-xl border border-line-strong bg-surface p-1.5 shadow-raised">
          <p className="px-3 pt-1.5 pb-1 text-[11px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Notifications</p>
          {inbox === null ? (
            <p className="px-3 py-3 text-sm text-fg-muted">Loading…</p>
          ) : inbox.items.length === 0 ? (
            <p className="px-3 py-3 text-sm text-fg-muted">Nothing yet. When your work is ready, or if it stops, it appears here.</p>
          ) : (
            inbox.items.map((item) => (
              <Menu.Item key={item.id} asChild>
                <Link to={item.to} className="flex gap-2.5 rounded-lg px-3 py-2 outline-none data-[highlighted]:bg-surface-muted">
                  {item.outcome === 'READY'
                    ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
                    : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />}
                  <span className="min-w-0 flex-1">
                    <span className={clsx('block text-sm text-fg', item.unread && 'font-semibold')}>{item.title}</span>
                    {item.detail && <span className="block text-xs text-fg-muted">{item.detail}</span>}
                    <span className="block text-xs text-fg-subtle">{when(item.at)}</span>
                  </span>
                  {item.unread && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand-600" aria-label="Unread" />}
                </Link>
              </Menu.Item>
            ))
          )}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  )
}
