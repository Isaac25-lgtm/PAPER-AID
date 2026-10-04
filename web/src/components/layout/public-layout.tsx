import { clsx } from 'clsx'
import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { useAuth } from '../../features/auth/auth-context'
import { ButtonLink } from '../ui/button'
import { Drawer } from '../ui/overlays'
import { Logo, LogoMark } from './logo'

const NAV = [
  { to: '/features', label: 'Product' },
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
          'sticky top-0 z-40 border-b bg-white/95 backdrop-blur-xl transition-colors',
          scrolled ? 'border-line' : 'border-transparent',
        )}
      >
        <div className="mx-auto flex h-[72px] max-w-[65rem] items-center justify-between gap-6 px-4 sm:px-6 lg:px-0">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    'rounded-lg px-3 py-1 text-[15px] tracking-[-0.01em] transition-colors hover:bg-surface-muted hover:text-fg',
                    isActive && !item.to.includes('#') ? 'text-fg' : 'text-fg-muted',
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
    <footer className="bg-[#030712] text-[#98a1ae]">
      <div className="mx-auto grid max-w-[65rem] gap-12 px-4 py-16 sm:px-6 md:grid-cols-[1.6fr_1fr_1fr] lg:px-0">
        <div>
          <div className="flex items-center gap-2.5">
            <LogoMark className="size-7" />
            <span className="text-lg font-semibold text-white">PaperAid</span>
          </div>
          <p className="mt-3 max-w-xs text-[15px] text-[#d1d5dc]">From first idea to finished paper, for researchers and students.</p>
          <Link to="/app/new" className="mt-5 inline-flex h-9 items-center rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-500">Get started</Link>
        </div>
        <div>
          <h2 className="text-[15px] font-semibold text-white">Product</h2>
          <ul className="mt-4 space-y-2.5 text-[15px]">
            <li><Link to="/features" className="hover:text-white">What PaperAid does</Link></li>
            <li><Link to="/#how-it-works" className="hover:text-white">How it works</Link></li>
            <li><Link to="/pricing" className="hover:text-white">Pricing</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="text-[15px] font-semibold text-white">Trust</h2>
          <ul className="mt-4 space-y-2.5 text-[15px]">
            <li><Link to="/privacy" className="hover:text-white">Privacy</Link></li>
            <li><Link to="/terms" className="hover:text-white">Terms</Link></li>
            <li><Link to="/features#what-we-never-do" className="hover:text-white">What we never change</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <p className="mx-auto max-w-[65rem] px-4 py-6 text-[13px] sm:px-6 lg:px-0">
          © 2026 PaperAid. PaperAid gives feedback on how writing reads; it does not detect AI, and no detector can prove who wrote a text. PaperAid is
          not affiliated with any detection service.
        </p>
      </div>
    </footer>
  )
}
