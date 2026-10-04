import * as Menu from '@radix-ui/react-dropdown-menu'
import { clsx } from 'clsx'
import { ChevronDown, FolderOpen, LayoutDashboard, LogOut, Menu as MenuIcon, Plus, Settings, ShieldCheck, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { TermsDialog } from '../../features/account/terms'
import { useAuth } from '../../features/auth/auth-context'
import { useData } from '../../lib/data'
import { formatTokenNumber } from '../../lib/format'
import { startChoices } from '../../lib/start'
import { useWallet } from '../../lib/use-wallet'
import { Drawer } from '../ui/overlays'
import { Logo } from './logo'

/** The top bar (owner decision 2026-10-01): Dashboard · New · Your work · credits. Every service is
 *  one click away under New; the full catalogue is the New page itself. */
export function AppLayout() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { config } = useData()
  const { wallet } = useWallet()
  const choices = startChoices(config)

  useEffect(() => setMenuOpen(false), [location.pathname, location.search])

  const onNew = location.pathname.startsWith('/app/new') || location.pathname.startsWith('/app/start')
  const onWork = ['/app/work', '/app/works', '/app/projects', '/app/jobs', '/app/history'].some((p) => location.pathname.startsWith(p))
  const links = [
    { to: '/app', label: 'Dashboard', icon: LayoutDashboard, active: location.pathname === '/app' },
    { to: '/app/work', label: 'Your work', icon: FolderOpen, active: onWork },
  ]

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  const initials = (user?.displayName || user?.email || '?').slice(0, 2).toUpperCase()
  const linkClass = (active: boolean) =>
    clsx(
      'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-brand-600',
      active ? 'bg-brand-50 text-brand-800' : 'text-fg-muted hover:bg-surface-muted hover:text-fg',
    )

  return (
    <div className="flex min-h-dvh flex-col bg-surface-subtle">
      <header className="sticky top-0 z-40 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Logo to="/app" />
          <nav aria-label="App" className="ml-2 hidden items-center gap-1 md:flex">
            <Link to={links[0].to} aria-current={links[0].active ? 'page' : undefined} className={linkClass(links[0].active)}>
              <LayoutDashboard className="size-4" aria-hidden /> Dashboard
            </Link>
            <Menu.Root>
              <Menu.Trigger className={linkClass(onNew)} aria-current={onNew ? 'page' : undefined}>
                <Plus className="size-4" aria-hidden /> New <ChevronDown className="size-3.5" aria-hidden />
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Content align="start" sideOffset={8} className="z-50 w-80 rounded-xl border border-line bg-white p-1.5 shadow-raised">
                  {choices.map((c) => (
                    <Menu.Item key={c.id} asChild>
                      <Link to={c.to} className="flex items-start gap-3 rounded-lg px-3 py-2.5 outline-none data-[highlighted]:bg-brand-50">
                        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
                          <c.icon className="size-4" aria-hidden />
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-fg">{c.name}</span>
                          <span className="block text-xs text-fg-muted">{c.short}</span>
                        </span>
                      </Link>
                    </Menu.Item>
                  ))}
                  <Menu.Separator className="my-1 h-px bg-line" />
                  <Menu.Item asChild>
                    <Link to="/app/new" className="block rounded-lg px-3 py-2 text-sm font-semibold text-brand-700 outline-none data-[highlighted]:bg-brand-50">
                      See every service
                    </Link>
                  </Menu.Item>
                </Menu.Content>
              </Menu.Portal>
            </Menu.Root>
            <Link to={links[1].to} aria-current={links[1].active ? 'page' : undefined} className={linkClass(links[1].active)}>
              <FolderOpen className="size-4" aria-hidden /> Your work
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {config.creditsEnabled && wallet && <CreditsPill available={wallet.available} held={wallet.held} />}
            {config.creditsEnabled && (
              <Link
                to="/app/credits"
                className="hidden items-center gap-1 rounded-lg bg-brand-700 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 sm:inline-flex"
              >
                <Plus className="size-4" aria-hidden /> Buy
              </Link>
            )}
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
                  {config.creditsEnabled && (
                    <Menu.Item asChild>
                      <Link to="/app/credits" className="flex items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted">
                        <Wallet className="size-4 text-fg-subtle" /> Credits
                      </Link>
                    </Menu.Item>
                  )}
                  {user?.isAdmin && (
                    <Menu.Item asChild>
                      <Link to="/admin" className="flex items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted">
                        <ShieldCheck className="size-4 text-fg-subtle" /> Admin
                      </Link>
                    </Menu.Item>
                  )}
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
        <nav aria-label="App mobile" className="flex flex-col gap-1">
          {links.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={item.active ? 'page' : undefined}
              className={clsx('flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium', item.active ? 'bg-brand-50 text-brand-800' : 'text-fg hover:bg-surface-muted')}
            >
              <item.icon className="size-5" aria-hidden /> {item.label}
            </Link>
          ))}
          <p className="mt-3 px-3 text-xs font-semibold tracking-wide text-fg-subtle uppercase">New</p>
          {choices.map((c) => (
            <Link key={c.id} to={c.to} className="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              <c.icon className="size-5 text-brand-700" aria-hidden /> {c.name}
            </Link>
          ))}
          <div className="my-2 h-px bg-line" />
          {config.creditsEnabled && (
            <Link to="/app/credits" className="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              <Wallet className="size-5" aria-hidden /> Credits{wallet ? `: ${formatTokenNumber(wallet.available)}` : ''}
            </Link>
          )}
          {user?.isAdmin && (
            <Link to="/admin" className="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              <ShieldCheck className="size-5" aria-hidden /> Admin
            </Link>
          )}
          <Link to="/app/settings" className="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium text-fg hover:bg-surface-muted">
            <Settings className="size-5" aria-hidden /> Settings
          </Link>
          <button onClick={handleSignOut} className="flex items-center gap-3 rounded-lg px-3 py-3 text-left text-base font-medium text-fg hover:bg-surface-muted">
            <LogOut className="size-5" aria-hidden /> Sign out
          </button>
        </nav>
      </Drawer>

      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
      <TermsDialog />
    </div>
  )
}

/** The balance, with what is reserved for running work (owner decision 2026-10-01: credits go down
 *  by themselves; a reservation is shown as reserved, never as used, until the document exists). */
function CreditsPill({ available, held }: { available: number; held: number }) {
  return (
    <Link
      to="/app/credits"
      className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm font-semibold whitespace-nowrap text-fg shadow-card hover:border-brand-300"
      aria-label={`Credits: ${formatTokenNumber(available)}${held > 0 ? `, ${formatTokenNumber(held)} reserved` : ''}`}
    >
      <span className="size-2 rounded-full bg-brand-600" aria-hidden />
      {formatTokenNumber(available)} credits
      {held > 0 && <span className="hidden text-xs font-medium text-fg-muted sm:inline">· {formatTokenNumber(held)} reserved</span>}
    </Link>
  )
}
