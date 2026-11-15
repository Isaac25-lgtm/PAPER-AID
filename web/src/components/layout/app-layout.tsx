import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import type { LucideIcon } from 'lucide-react'
import { FileCheck2, FilePen, FolderOpen, HandCoins, House, Lightbulb, LogOut, Menu as MenuIcon, Monitor, Moon, NotebookPen, Plus, ScanSearch, ScrollText, Search, Settings, ShieldCheck, Sun, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { TermsDialog } from '../../features/account/terms'
import { useAuth } from '../../features/auth/auth-context'
import { YourWorkProvider } from '../../features/jobs/your-work-data'
import { useData } from '../../lib/data'
import { formatTokenNumber } from '../../lib/format'
import { startChoices } from '../../lib/start'
import { useAppearance, type Appearance } from '../../lib/theme'
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
  /** Shown greyed as "Coming soon" while its service is announced but not built, and never a link. */
  soon?: boolean
}

const HOME: NavItem[] = [
  { to: '/app', label: 'Home', icon: House, active: (p) => p === '/app' },
  { to: '/app/work', label: 'Your work', icon: FolderOpen, active: (p) => p === '/app/work' || p.startsWith('/app/jobs') || p.startsWith('/app/history') },
]

const on = (s: string, value: string) => new URLSearchParams(s).get('section') === value

/** One list of sections, the same for researchers and students (owner decision 2026-10-04), each service its own
 *  section in the owner's order (2026-11-15: coursework and funding were never to be mixed), then the AI checker,
 *  announced and not yet built, then the person's own paper. */
const SECTIONS_NAV: NavItem[] = [
  { to: '/app/works?section=COURSEWORK', label: 'Coursework', icon: NotebookPen, service: 'COURSEWORK',
    active: (p, s) => p === '/app/works' && (!new URLSearchParams(s).get('section') || on(s, 'COURSEWORK')) },
  { to: '/app/projects?goal=CONCEPT', label: 'Research concept note', icon: Lightbulb, service: 'PROPOSAL',
    active: (p, s) => p === '/app/projects' && new URLSearchParams(s).get('goal') === 'CONCEPT' },
  { to: '/app/projects', label: 'Research proposal', icon: FilePen, service: 'PROPOSAL',
    active: (p, s) => p === '/app/projects' && new URLSearchParams(s).get('goal') !== 'CONCEPT' },
  { to: '/app/works?section=CONCEPT_NOTE', label: 'Funding concept note', icon: ScrollText, service: 'CONCEPT_NOTE', active: (p, s) => p === '/app/works' && on(s, 'CONCEPT_NOTE') },
  { to: '/app/works?section=FUNDING_PROPOSAL', label: 'Funding proposal', icon: HandCoins, service: 'FUNDING_PROPOSAL', active: (p, s) => p === '/app/works' && on(s, 'FUNDING_PROPOSAL') },
  { to: '', label: 'AI checker', icon: ScanSearch, service: 'AI_CHECK', soon: true, active: () => false },
  { to: '/app/new?service=PAPER_CHECK', label: 'Paper Check', icon: Search, service: 'REFINE', active: (p, s) => p === '/app/new' && s.includes('PAPER_CHECK') },
  { to: '/app/new?service=ACADEMIC_FORMAT', label: 'Academic formatting', icon: FileCheck2, service: 'FORMAT', active: (p, s) => p === '/app/new' && s.includes('ACADEMIC_FORMAT') },
]

/** The app shell (redesign 2026-10-04, after Jenni's calm): a left sidebar with New, Home, Your work and the
 *  sections; the work in the middle on white; the credit balance always in the top bar. On phones the
 *  sidebar is a drawer. The left panel holds the sections only; the person's recent work is on the dashboard
 *  (owner, 2026-11-15, replacing the rule of 2026-10-10). */
export function AppLayout() {
  return (
    <YourWorkProvider>
      <Shell />
    </YourWorkProvider>
  )
}

function Shell() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { config } = useData()
  const { wallet } = useWallet()
  const choices = startChoices(config)
  const [appearance, setAppearance] = useAppearance()

  useEffect(() => setMenuOpen(false), [location.pathname, location.search])

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }
  const offered = (item: NavItem) => !item.service || (config.availability[item.service] && config.availability[item.service] !== 'soon')
  // the AI checker is listed only while its service is announced as coming (availability 'soon')
  const sections = SECTIONS_NAV.filter((item) => (item.soon ? item.service !== undefined && config.availability[item.service] === 'soon' : offered(item)))
  const initials = (user?.displayName || user?.email || '?').slice(0, 2).toUpperCase()
  const navLink = (item: NavItem, big = false) => {
    const active = item.active(location.pathname, location.search)
    return (
      <Link key={item.to} to={item.to} aria-current={active ? 'page' : undefined}
        className={clsx('flex items-center gap-2.5 rounded-lg px-2.5 font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand-600',
          big ? 'py-3 text-base' : 'py-1.5 text-sm',
          active ? 'bg-brand-50 text-brand-700' : 'text-fg hover:bg-surface-muted')}>
        <item.icon className={clsx(big ? 'size-5' : 'size-[18px]', active ? 'text-brand-600' : 'text-fg-muted')} aria-hidden /> {item.label}
      </Link>
    )
  }

  /** A service announced but not built yet: greyed, labelled, and not a link (no placeholder page behind it). */
  const soonItem = (item: NavItem, big = false) => (
    <div key={item.label} aria-disabled="true" title="Coming soon"
      className={clsx('flex cursor-default items-center gap-2.5 rounded-lg px-2.5 font-medium text-fg-subtle', big ? 'py-3 text-base' : 'py-1.5 text-sm')}>
      <item.icon className={clsx(big ? 'size-5' : 'size-[18px]', 'text-fg-subtle/70')} aria-hidden />
      <span className="flex-1">{item.label}</span>
      <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-fg-subtle ring-1 ring-line">Coming soon</span>
    </div>
  )

  const newMenu = (
    <Menu.Root>
      <Menu.Trigger className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-3 text-[15px] font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15),0_1px_2px_rgb(16_24_40/0.08)] transition-colors hover:bg-brand-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
        <Plus className="size-4" aria-hidden /> New
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="start" side="right" sideOffset={10} className="z-50 w-80 rounded-xl border border-line bg-surface p-1.5 shadow-raised">
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
        <Menu.Content align="start" side="top" sideOffset={8} className="z-50 w-60 rounded-xl border border-line bg-surface p-1.5 shadow-raised">
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
      <div className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-line-strong bg-surface-subtle lg:flex">
        <div className="flex h-14 items-center px-4">
          <Logo to="/app" />
        </div>
        <div className="px-3 pb-3">{newMenu}</div>
        <nav aria-label="App" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3">
          {HOME.map((item) => navLink(item))}
          {sections.length > 0 && <p className="mt-5 mb-1 px-2.5 text-[11px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Sections</p>}
          {sections.map((item) => (item.soon ? soonItem(item) : navLink(item)))}
        </nav>
        <div className="flex flex-col gap-0.5 border-t border-line-strong px-3 py-3">
          {footerLinks.map((item) => navLink(item))}
          <AppearanceSwitch value={appearance} onChange={setAppearance} />
          <div className="mt-1">{account}</div>
        </div>
      </div>

      <div className="flex min-h-dvh flex-col lg:pl-[248px]">
        <header className={clsx('sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur', !config.creditsEnabled && 'lg:hidden')}>
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
                  className="hidden h-8 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[13px] font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] hover:bg-brand-strong sm:inline-flex">
                  <Plus className="size-3.5" aria-hidden /> Buy
                </Link>
              )}
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
        <footer className="border-t border-line-strong bg-surface-subtle">
          <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-5 text-sm text-fg-muted sm:px-8">
            <span>© {new Date().getFullYear()} PaperAid</span>
            <Link to="/terms" className="hover:text-fg hover:underline">Terms</Link>
            <Link to="/privacy" className="hover:text-fg hover:underline">Privacy</Link>
            <Link to="/pricing" className="hover:text-fg hover:underline">Pricing</Link>
          </div>
        </footer>
      </div>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} title={user?.email ?? 'Menu'}>
        <nav aria-label="App mobile" className="flex flex-col gap-0.5">
          {HOME.map((item) => navLink(item, true))}
          {sections.length > 0 && <p className="mt-4 mb-1 px-2.5 text-xs font-semibold tracking-[0.08em] text-fg-subtle uppercase">Sections</p>}
          {sections.map((item) => (item.soon ? soonItem(item, true) : navLink(item, true)))}
          <p className="mt-4 mb-1 px-2.5 text-xs font-semibold tracking-[0.08em] text-fg-subtle uppercase">Start new</p>
          {choices.map((c) => (
            <Link key={c.id} to={c.to} className="flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              <c.icon className="size-5 text-fg-subtle" aria-hidden /> {c.name}
            </Link>
          ))}
          <div className="my-2 h-px bg-line" />
          {footerLinks.map((item) => navLink(item, true))}
          <AppearanceSwitch value={appearance} onChange={setAppearance} big />
          <button onClick={handleSignOut} className="flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-left text-base font-medium text-fg-muted hover:bg-surface-muted">
            <LogOut className="size-5 text-fg-subtle" aria-hidden /> Sign out
          </button>
        </nav>
      </Drawer>
      <TermsDialog />
    </div>
  )
}

const APPEARANCES: { value: Appearance; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Day', icon: Sun },
  { value: 'dark', label: 'Night', icon: Moon },
  { value: 'system', label: 'Same as this device', icon: Monitor },
]

/** Day, night or the device's own setting (owner, 2026-11-15), as three small buttons beside the word Appearance. */
function AppearanceSwitch({ value, onChange, big = false }: { value: Appearance; onChange: (value: Appearance) => void; big?: boolean }) {
  return (
    <div className={clsx('flex items-center justify-between gap-2 px-2.5', big ? 'py-2' : 'py-1')}>
      <span className={clsx('font-medium text-fg-muted', big ? 'text-base' : 'text-sm')} id={big ? 'appearance-mobile' : 'appearance'}>Appearance</span>
      <div role="radiogroup" aria-labelledby={big ? 'appearance-mobile' : 'appearance'} className="flex items-center gap-0.5 rounded-lg border border-line-strong bg-surface p-0.5">
        {APPEARANCES.map((a) => {
          const on = a.value === value
          return (
            <button key={a.value} type="button" role="radio" aria-checked={on} aria-label={a.label} title={a.label} onClick={() => onChange(a.value)}
              className={clsx('grid place-items-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-brand-600', big ? 'size-9' : 'size-7',
                on ? 'bg-fg text-surface' : 'text-fg-subtle hover:bg-surface-muted hover:text-fg')}>
              <a.icon className="size-4" aria-hidden />
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** The balance, with what is reserved for running work (owner decision 2026-10-01: credits go down
 *  by themselves; a reservation is shown as reserved, never as used, until the document exists). */
function CreditsPill({ available, held }: { available: number; held: number }) {
  return (
    <Link
      to="/app/credits"
      className="inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium whitespace-nowrap text-fg hover:border-line-strong"
      aria-label={`Credits: ${formatTokenNumber(available)}${held > 0 ? `, ${formatTokenNumber(held)} reserved` : ''}`}
    >
      <span className="size-1.5 rounded-full bg-brand-600" aria-hidden />
      {formatTokenNumber(available)} credits
      {held > 0 && <span className="hidden text-xs text-fg-subtle sm:inline">· {formatTokenNumber(held)} reserved</span>}
    </Link>
  )
}
