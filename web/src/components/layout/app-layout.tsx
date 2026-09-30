import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import { FileCheck2, GraduationCap, History, LayoutDashboard, LogOut, Menu as MenuIcon, Plus, Search, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../../features/auth/auth-context'
import { useData } from '../../lib/data'
import { formatTokens } from '../../lib/format'
import type { ServiceId } from '../../lib/types'
import { useWallet } from '../../lib/use-wallet'
import { ButtonLink } from '../ui/button'
import { Drawer } from '../ui/overlays'
import { Logo } from './logo'

export function AppLayout() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { config } = useData()
  const { wallet } = useWallet()

  useEffect(() => setMenuOpen(false), [location.pathname, location.search])

  // The three sections are one click away from anywhere (owner decision 2026-09-29).
  const service = new URLSearchParams(location.search).get('service') ?? (new URLSearchParams(location.search).get('review') ? 'PROPOSAL_REVIEW' : '')
  const onNew = (...ids: string[]) => location.pathname === '/app/new' && ids.includes(service)
  const offered = (id: ServiceId) => config.availability[id] !== 'soon'
  const nav: { to: string; label: string; icon: typeof History; active: boolean; mobileOnly?: boolean }[] = [
    { to: '/app', label: 'Dashboard', icon: LayoutDashboard, active: location.pathname === '/app' },
    ...(offered('AI_CHECK')
      ? [{ to: '/app/new?service=PAPER_CHECK', label: 'Paper Check', icon: Search, active: onNew('PAPER_CHECK', 'AI_CHECK', 'REFINE', 'REDRAFT', 'SOURCE_CHECK') }]
      : []),
    ...(offered('PROPOSAL')
      ? [{ to: '/app/projects', label: 'Research Proposals', icon: GraduationCap, active: location.pathname.startsWith('/app/projects') || onNew('PROPOSAL_REVIEW') }]
      : []),
    ...(offered('FORMAT')
      ? [{ to: '/app/new?service=ACADEMIC_FORMAT', label: 'Academic Formatting', icon: FileCheck2, active: onNew('ACADEMIC_FORMAT', 'FORMAT', 'TEMPLATE_FORMAT', 'LATEX') }]
      : []),
    { to: '/app/history', label: 'History', icon: History, active: location.pathname.startsWith('/app/history') || location.pathname.startsWith('/app/jobs') },
    ...(config.creditsEnabled ? [{ to: '/app/credits', label: 'Tokens', icon: Wallet, active: location.pathname.startsWith('/app/credits'), mobileOnly: true }] : []),
    ...(user?.isAdmin ? [{ to: '/admin', label: 'Admin', icon: ShieldCheck, active: location.pathname.startsWith('/admin') }] : []),
  ]

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  const initials = (user?.displayName || user?.email || '?').slice(0, 2).toUpperCase()

  return (
    <div className="flex min-h-dvh flex-col bg-surface-subtle">
      <header className="sticky top-0 z-40 border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Logo to="/app" />
          <nav aria-label="App" className="hidden items-center gap-0.5 lg:flex">
            {nav.filter((item) => !item.mobileOnly).map((item) => (
              <Link
                key={item.to}
                to={item.to}
                aria-current={item.active ? 'page' : undefined}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-md px-2.5 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                  item.active ? 'bg-brand-50 text-brand-800' : 'text-fg-muted hover:bg-surface-muted hover:text-fg',
                )}
              >
                <item.icon className="size-4" aria-hidden />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {config.creditsEnabled && wallet && (
              <Link
                to="/app/credits"
                className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold whitespace-nowrap text-brand-800 ring-1 ring-brand-200 hover:bg-brand-100"
                aria-label={`Tokens: ${formatTokens(wallet.available)}`}
              >
                <Wallet className="size-3.5" aria-hidden /> {formatTokens(wallet.available)}
              </Link>
            )}
            <ButtonLink to="/app/new" size="sm" className="hidden sm:inline-flex">
              <Plus className="size-4" aria-hidden />
              New job
            </ButtonLink>
            <Menu.Root>
              <Menu.Trigger
                className="hidden size-9 place-items-center rounded-full bg-brand-100 text-xs font-bold text-brand-800 ring-brand-300 hover:ring-2 lg:grid"
                aria-label="Account menu"
              >
                {initials}
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Content align="end" sideOffset={8} className="z-50 w-60 rounded-xl border border-line bg-white p-1.5 shadow-raised">
                  <div className="px-3 py-2">
                    <p className="truncate text-sm font-semibold">{user?.displayName}</p>
                    <p className="truncate text-xs text-fg-subtle">{user?.email}</p>
                  </div>
                  <Menu.Separator className="my-1 h-px bg-line" />
                  <Menu.Item asChild>
                    <Link to="/app/settings" className="flex items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted">
                      <Settings className="size-4 text-fg-subtle" /> Settings
                    </Link>
                  </Menu.Item>
                  <Menu.Item
                    onSelect={handleSignOut}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted"
                  >
                    <LogOut className="size-4 text-fg-subtle" /> Sign out
                  </Menu.Item>
                </Menu.Content>
              </Menu.Portal>
            </Menu.Root>
            <button className="rounded-md p-2 text-fg-muted hover:bg-surface-muted lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <MenuIcon className="size-5" />
            </button>
          </div>
        </div>
      </header>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} title={user?.email ?? 'Menu'}>
        <ButtonLink to="/app/new" className="mb-4 w-full">
          <Plus className="size-4" aria-hidden /> New job
        </ButtonLink>
        <nav aria-label="App mobile" className="flex flex-col gap-1">
          {[...nav, { to: '/app/settings', label: 'Settings', icon: Settings, active: location.pathname.startsWith('/app/settings') }].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={item.active ? 'page' : undefined}
              className={clsx('flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium', item.active ? 'bg-brand-50 text-brand-800' : 'text-fg hover:bg-surface-muted')}
            >
              <item.icon className="size-5" aria-hidden /> {item.label}
            </Link>
          ))}
          <button onClick={handleSignOut} className="flex items-center gap-3 rounded-lg px-3 py-3 text-left text-base font-medium text-fg hover:bg-surface-muted">
            <LogOut className="size-5" aria-hidden /> Sign out
          </button>
        </nav>
      </Drawer>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
