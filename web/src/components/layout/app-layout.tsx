import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import type { LucideIcon } from 'lucide-react'
import { ChartColumn, FileCheck2, FilePen, FolderOpen, House, LogOut, Menu as MenuIcon, NotebookPen, Plus, Search, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { TermsDialog } from '../../features/account/terms'
import { useAuth } from '../../features/auth/auth-context'
import { YourWorkProvider, pendingFirst, useYourWork, type WorkItem } from '../../features/jobs/your-work-data'
import { useData } from '../../lib/data'
import { formatTokenNumber } from '../../lib/format'
import { startChoices } from '../../lib/start'
import type { StartChoice } from '../../lib/start'
import type { ServiceId } from '../../lib/types'
import { useWallet } from '../../lib/use-wallet'
import { Drawer } from '../ui/overlays'
import { Logo } from './logo'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  active: (path: string, search: string) => boolean
  service?: ServiceId // shown only when this service is offered
  groups?: StartChoice['group'][] // the student's work listed under it in the left panel
}

const LISTED = 4 // pieces of work shown under a section; the rest are one click away

const HOME: NavItem[] = [
  { to: '/app', label: 'Home', icon: House, active: (p) => p === '/app' },
  { to: '/app/work', label: 'Your work', icon: FolderOpen, active: (p) => p === '/app/work' || p.startsWith('/app/jobs') || p.startsWith('/app/history') },
]

/** One list of sections, the same for researchers and students (owner decision 2026-10-04). */
const SECTIONS_NAV: NavItem[] = [
  { to: '/app/works', label: 'Coursework & funding', icon: NotebookPen, service: 'COURSEWORK', active: (p) => p.startsWith('/app/works'), groups: ['Coursework', 'Funding'] },
  { to: '/app/projects', label: 'Research proposals', icon: FilePen, service: 'PROPOSAL', active: (p) => p.startsWith('/app/projects'), groups: ['Research proposals'] },
  { to: '/app/datalab', label: 'Data Lab', icon: ChartColumn, service: 'DATALAB', active: (p) => p.startsWith('/app/datalab'), groups: ['Data analysis'] },
  { to: '/app/new?service=PAPER_CHECK', label: 'Paper Check', icon: Search, service: 'REFINE', active: (p, s) => p === '/app/new' && s.includes('PAPER_CHECK') },
  { to: '/app/new?service=ACADEMIC_FORMAT', label: 'Academic formatting', icon: FileCheck2, service: 'FORMAT', active: (p, s) => p === '/app/new' && s.includes('ACADEMIC_FORMAT') },
]

/** The app shell (redesign 2026-10-04, after Jenni's calm): a left sidebar with New, Home, Your work and the
 *  sections; the work in the middle on white; the credit balance always in the top bar. On phones the
 *  sidebar is a drawer. The student's own work is listed in the left panel under its section, what is pending
 *  first (owner, 2026-10-10), so the dashboard only shows what can be started. */
export function AppLayout() {
  return (
    <YourWorkProvider>
      <Shell />
    </YourWorkProvider>
  )
}

function Shell() {
  const { user, signOut } = useAuth()
  const { items, error: workError } = useYourWork()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { config } = useData()
  const { wallet } = useWallet()
  const choices = startChoices(config)

  useEffect(() => setMenuOpen(false), [location.pathname, location.search])

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }
  const offered = (item: NavItem) => !item.service || (config.availability[item.service] && config.availability[item.service] !== 'soon')
  const sections = SECTIONS_NAV.filter(offered)
  const initials = (user?.displayName || user?.email || '?').slice(0, 2).toUpperCase()
  const navLink = (item: NavItem, big = false) => {
    const active = item.active(location.pathname, location.search)
    return (
      <Link key={item.to} to={item.to} aria-current={active ? 'page' : undefined}
        className={clsx('flex items-center gap-2.5 rounded-lg px-2.5 font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand-600',
          big ? 'py-3 text-base' : 'py-1.5 text-sm',
          active ? 'bg-brand-50 text-brand-700' : 'text-fg-muted hover:bg-surface-muted hover:text-fg')}>
        <item.icon className={clsx(big ? 'size-5' : 'size-[18px]', active ? 'text-brand-600' : 'text-fg-subtle')} aria-hidden /> {item.label}
      </Link>
    )
  }

  /** A section with the student's work under it: pending first, then done, the newest of each. */
  const sectionBlock = (item: NavItem, big = false) => {
    const mine = pendingFirst((items ?? []).filter((i) => item.groups?.includes(i.group)))
    return (
      <div key={item.to}>
        {navLink(item, big)}
        {mine.length > 0 && (
          <ul className={clsx('mt-0.5 mb-1.5 border-l border-line', big ? 'ml-5 pl-2' : 'ml-[19px] pl-2')}>
            {mine.slice(0, LISTED).map((work) => (
              <li key={work.key}>
                <WorkLink work={work} active={location.pathname === work.to} big={big} />
              </li>
            ))}
            {mine.length > LISTED && (
              <li>
                <Link to="/app/work" className={clsx('block rounded-md px-2 py-1 font-medium text-brand-700 hover:underline', big ? 'text-sm' : 'text-xs')}>
                  See all {mine.length}
                </Link>
              </li>
            )}
          </ul>
        )}
      </div>
    )
  }

  const newMenu = (
    <Menu.Root>
      <Menu.Trigger className="flex h-9 w-full items-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-medium text-fg shadow-[0_1px_2px_rgb(16_24_40/0.04)] hover:border-line-strong focus-visible:outline-2 focus-visible:outline-brand-600">
        <Plus className="size-4 text-brand-600" aria-hidden /> New
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="start" side="right" sideOffset={10} className="z-50 w-80 rounded-xl border border-line bg-white p-1.5 shadow-raised">
          <p className="px-3 pt-1.5 pb-1 text-[11px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Start new</p>
          {choices.map((c) => (
            <Menu.Item key={c.id} asChild>
              <Link to={c.to} className="flex items-start gap-3 rounded-lg px-3 py-2 outline-none data-[highlighted]:bg-surface-muted">
                <c.icon className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden />
                <span>
                  <span className="block text-sm font-medium text-fg">{c.name}</span>
                  <span className="block text-xs text-fg-subtle">{c.short}</span>
                </span>
              </Link>
            </Menu.Item>
          ))}
          <Menu.Separator className="my-1 h-px bg-line" />
          <Menu.Item asChild>
            <Link to="/app/new" className="block rounded-lg px-3 py-2 text-sm font-medium text-brand-700 outline-none data-[highlighted]:bg-surface-muted">
              See every service
            </Link>
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  )

  const account = (
    <Menu.Root>
      <Menu.Trigger className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-brand-600" aria-label="Account menu">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-100 text-[11px] font-semibold text-brand-700">{initials}</span>
        <span className="min-w-0 flex-1 truncate text-sm text-fg-muted">{user?.email}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="start" side="top" sideOffset={8} className="z-50 w-60 rounded-xl border border-line bg-white p-1.5 shadow-raised">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{user?.displayName}</p>
            <p className="truncate text-xs text-fg-subtle">{user?.email}</p>
          </div>
          <Menu.Separator className="my-1 h-px bg-line" />
          <Menu.Item onSelect={handleSignOut} className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted">
            <LogOut className="size-4 text-fg-subtle" /> Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  )

  const footerLinks: NavItem[] = [
    ...(config.creditsEnabled ? [{ to: '/app/credits', label: 'Credits', icon: Wallet, active: (p: string) => p.startsWith('/app/credits') }] : []),
    ...(user?.isAdmin ? [{ to: '/admin', label: 'Admin', icon: ShieldCheck, active: (p: string) => p.startsWith('/admin') }] : []),
    { to: '/app/settings', label: 'Settings', icon: Settings, active: (p: string) => p.startsWith('/app/settings') },
  ]

  return (
    <div className="min-h-dvh bg-surface">
      <div className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-line bg-surface-subtle lg:flex">
        <div className="flex h-14 items-center px-4">
          <Logo to="/app" />
        </div>
        <div className="px-3 pb-3">{newMenu}</div>
        <nav aria-label="App" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3">
          {HOME.map((item) => navLink(item))}
          {sections.length > 0 && <p className="mt-5 mb-1 px-2.5 text-[11px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Sections</p>}
          {sections.map((item) => sectionBlock(item))}
          {workError && <p className="mt-2 px-2.5 text-xs text-fg-subtle" role="status">{items ? 'Your work could not be refreshed just now.' : 'Your work could not be loaded.'}</p>}
        </nav>
        <div className="flex flex-col gap-0.5 border-t border-line px-3 py-3">
          {footerLinks.map((item) => navLink(item))}
          <div className="mt-1">{account}</div>
        </div>
      </div>

      <div className="flex min-h-dvh flex-col lg:pl-[248px]">
        <header className={clsx('sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur', !config.creditsEnabled && 'lg:hidden')}>
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <button className="-ml-1 rounded-lg p-2 text-fg-muted hover:bg-surface-muted lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <MenuIcon className="size-5" />
            </button>
            <div className="lg:hidden">
              <Logo to="/app" />
            </div>
            <div className="ml-auto flex items-center gap-2">
              {config.creditsEnabled && wallet && <CreditsPill available={wallet.available} held={wallet.held} />}
              {config.creditsEnabled && (
                <Link to="/app/credits"
                  className="hidden h-8 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[13px] font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] hover:bg-brand-700 sm:inline-flex">
                  <Plus className="size-3.5" aria-hidden /> Buy
                </Link>
              )}
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
      </div>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} title={user?.email ?? 'Menu'}>
        <nav aria-label="App mobile" className="flex flex-col gap-0.5">
          {HOME.map((item) => navLink(item, true))}
          {sections.length > 0 && <p className="mt-4 mb-1 px-2.5 text-xs font-semibold tracking-[0.08em] text-fg-subtle uppercase">Sections</p>}
          {sections.map((item) => sectionBlock(item, true))}
          <p className="mt-4 mb-1 px-2.5 text-xs font-semibold tracking-[0.08em] text-fg-subtle uppercase">Start new</p>
          {choices.map((c) => (
            <Link key={c.id} to={c.to} className="flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              <c.icon className="size-5 text-fg-subtle" aria-hidden /> {c.name}
            </Link>
          ))}
          <div className="my-2 h-px bg-line" />
          {footerLinks.map((item) => navLink(item, true))}
          <button onClick={handleSignOut} className="flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-left text-base font-medium text-fg-muted hover:bg-surface-muted">
            <LogOut className="size-5 text-fg-subtle" aria-hidden /> Sign out
          </button>
        </nav>
      </Drawer>
      <TermsDialog />
    </div>
  )
}

/** One piece of the student's work in the left panel: a dot for where it is (being written, waiting, done), its title. */
function WorkLink({ work, active, big }: { work: WorkItem; active: boolean; big: boolean }) {
  const tone = work.status.tone
  const dot = tone === 'running' ? 'bg-brand-500 animate-pulse' : tone === 'ready' || tone === 'warn' ? 'bg-emerald-500' : tone === 'danger' ? 'bg-red-500' : 'bg-amber-400'
  return (
    <Link to={work.to} title={`${work.title} · ${work.status.label}`} aria-current={active ? 'page' : undefined}
      className={clsx('flex items-center gap-2 rounded-md px-2 transition-colors focus-visible:outline-2 focus-visible:outline-brand-600', big ? 'py-2 text-sm' : 'py-1 text-[13px]',
        active ? 'bg-brand-50 text-brand-700' : 'text-fg-muted hover:bg-surface-muted hover:text-fg')}>
      <span className={clsx('size-1.5 shrink-0 rounded-full', dot)} aria-hidden />
      <span className="min-w-0 flex-1 truncate">{work.title}</span>
      <span className="sr-only">{work.status.label}</span>
    </Link>
  )
}

/** The balance, with what is reserved for running work (owner decision 2026-10-01: credits go down
 *  by themselves; a reservation is shown as reserved, never as used, until the document exists). */
function CreditsPill({ available, held }: { available: number; held: number }) {
  return (
    <Link
      to="/app/credits"
      className="inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-white px-3 text-[13px] font-medium whitespace-nowrap text-fg hover:border-line-strong"
      aria-label={`Credits: ${formatTokenNumber(available)}${held > 0 ? `, ${formatTokenNumber(held)} reserved` : ''}`}
    >
      <span className="size-1.5 rounded-full bg-brand-600" aria-hidden />
      {formatTokenNumber(available)} credits
      {held > 0 && <span className="hidden text-xs text-fg-subtle sm:inline">· {formatTokenNumber(held)} reserved</span>}
    </Link>
  )
}
