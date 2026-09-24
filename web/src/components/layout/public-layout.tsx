import { clsx } from 'clsx'
import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { useAuth } from '../../features/auth/auth-context'
import { ButtonLink } from '../ui/button'
import { Drawer } from '../ui/overlays'
import { Logo, LogoMark } from './logo'

const NAV = [
  { to: '/features', label: 'Features' },
  { to: '/#how-it-works', label: 'How it works' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/privacy', label: 'Privacy' },
]

export function PublicLayout() {
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    setMenuOpen(false)
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView()
  }, [location.pathname, location.hash])

  const cta = user ? (
    <ButtonLink to="/app" size="sm">
      Go to dashboard
    </ButtonLink>
  ) : (
    <>
      <ButtonLink to="/sign-in" variant="secondary" size="sm">
        Sign in
      </ButtonLink>
      <ButtonLink to="/sign-up" size="sm">
        Get started
      </ButtonLink>
    </>
  )

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:shadow-raised">
        Skip to content
      </a>
      <header
        className={clsx(
          'sticky top-0 z-40 border-b bg-white/85 backdrop-blur-md transition-colors',
          scrolled ? 'border-line' : 'border-transparent',
        )}
      >
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors hover:text-fg',
                    isActive && !item.to.includes('#') ? 'text-brand-700' : 'text-fg-muted',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">{cta}</div>
          <button className="rounded-md p-2 text-fg-muted hover:bg-surface-muted md:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
        </div>
      </header>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} title="Menu">
        <nav aria-label="Mobile" className="flex flex-col gap-1">
          {NAV.map((item) => (
            <Link key={item.to} to={item.to} className="rounded-lg px-3 py-3 text-base font-medium text-fg hover:bg-surface-muted">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-6 flex flex-col gap-2 border-t border-line pt-6 [&>a]:w-full">{cta}</div>
      </Drawer>

      <main id="main" className="flex-1">
        <Outlet />
      </main>

      <SiteFooter />
    </div>
  )
}

function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface-subtle">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <LogoMark className="size-7" />
            <span className="text-lg font-bold">
              Paper<span className="text-brand-600">Aid</span>
            </span>
          </div>
          <p className="mt-3 max-w-xs text-sm text-fg-muted">Clear, correct, properly formatted papers — with your citations, data and voice left intact.</p>
        </div>
        <div>
          <h2 className="text-sm font-semibold">Product</h2>
          <ul className="mt-3 space-y-2 text-sm text-fg-muted">
            <li><Link to="/features" className="hover:text-fg">Features</Link></li>
            <li><Link to="/pricing" className="hover:text-fg">Pricing</Link></li>
            <li><Link to="/app/new" className="hover:text-fg">Upload a paper</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold">Trust</h2>
          <ul className="mt-3 space-y-2 text-sm text-fg-muted">
            <li><Link to="/privacy" className="hover:text-fg">Privacy</Link></li>
            <li><Link to="/features#what-we-never-do" className="hover:text-fg">What we never change</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-fg-subtle sm:px-6">
          © 2026 PaperAid. AI-likeness results are estimates; no AI detector can prove who wrote a text. PaperAid is not affiliated with any detection
          service.
        </p>
      </div>
    </footer>
  )
}
