import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import { History, LayoutDashboard, LogOut, Menu as MenuIcon, Plus, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../../features/auth/auth-context'
import { useData } from '../../lib/data'
import { formatUGX } from '../../lib/format'
import { useWallet } from '../../lib/use-wallet'
import { ButtonLink } from '../ui/button'
import { Drawer } from '../ui/overlays'
import { Logo } from './logo'

export function AppLayout() {
  const { user, signOut } = useAuth()
  const { config } = useData()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { wallet } = useWallet()

  useEffect(() => setMenuOpen(false), [location.pathname])

  const nav = [
    { to: '/app', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/app/history', label: 'History', icon: History, end: false },
    { to: '/app/credits', label: 'Credits', icon: Wallet, end: false },
    ...(user?.isAdmin ? [{ to: '/admin', label: 'Admin', icon: ShieldCheck, end: false }] : []),
  ]

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  const initials = (user?.displayName || user?.email || '?').slice(0, 2).toUpperCase()

  return (
    <div className="flex min-h-dvh flex-col bg-surface-subtle">
      {!config.paymentsEnabled && (
        <div className="bg-brand-800 px-4 py-2 text-center text-xs font-medium text-brand-50">
          PaperAid is in beta. Mobile-money top-ups aren&rsquo;t live yet, so PaperAid adds credits for you while we test.
        </div>
      )}
      <header className="sticky top-0 z-40 border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Logo to="/app" />
          <nav aria-label="App" className="hidden items-center gap-1 md:flex">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive ? 'bg-brand-50 text-brand-800' : 'text-fg-muted hover:bg-surface-muted hover:text-fg',
                  )
                }
              >
                <item.icon className="size-4" aria-hidden />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {wallet && (
              <Link
                to="/app/credits"
                className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-800 ring-1 ring-brand-200 hover:bg-brand-100"
                aria-label={`Credits: ${formatUGX(wallet.available)}`}
              >
                <Wallet className="size-3.5" aria-hidden /> {formatUGX(wallet.available)}
              </Link>
            )}
            <ButtonLink to="/app/new" size="sm" className="hidden sm:inline-flex">
              <Plus className="size-4" aria-hidden />
              New job
            </ButtonLink>
            <Menu.Root>
              <Menu.Trigger
                className="hidden size-9 place-items-center rounded-full bg-brand-100 text-xs font-bold text-brand-800 ring-brand-300 hover:ring-2 md:grid"
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
            <button className="rounded-md p-2 text-fg-muted hover:bg-surface-muted md:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <MenuIcon className="size-5" />
            </button>
          </div>
        </div>
      </header>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} title={user?.email ?? 'Menu'}>
        <ButtonLink to="/app/new" className="mb-4 w-full">
          <Plus className="size-4" aria-hidden /> New paper job
        </ButtonLink>
        <nav aria-label="App mobile" className="flex flex-col gap-1">
          {[...nav, { to: '/app/settings', label: 'Settings', icon: Settings, end: false }].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx('flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium', isActive ? 'bg-brand-50 text-brand-800' : 'text-fg hover:bg-surface-muted')
              }
            >
              <item.icon className="size-5" aria-hidden /> {item.label}
            </NavLink>
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
