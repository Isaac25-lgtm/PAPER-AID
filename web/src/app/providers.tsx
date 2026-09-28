import { Loader2, ServerCrash } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { LogoMark } from '../components/layout/logo'
import { AuthProvider, useAuth } from '../features/auth/auth-context'
import { createApiSource, fetchPublicConfig } from '../lib/api-source'
import { DataContext } from '../lib/data'
import type { PublicConfig } from '../lib/types'

function Splash({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-5 bg-surface-subtle px-4 text-center">
      <LogoMark className="size-10" />
      {children}
    </div>
  )
}

/** Shown only if starting up takes unusually long (a slow connection), so it never looks stuck. */
function SlowNote() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 4000)
    return () => clearTimeout(timer)
  }, [])
  return slow ? <p className="text-sm text-fg-muted">Connecting securely to PaperAid&hellip;</p> : null
}

function DataProvider({ children }: { children: ReactNode }) {
  const { getAuthHeaders, ready, user } = useAuth()
  const uid = user?.uid
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  // Fetched again whenever the signed-in user changes: availability can depend on who they are.
  useEffect(() => {
    if (!ready) return
    let cancelled = false
    setFailed(false)
    getAuthHeaders(false) // the services list needs only the sign-in token, never a reCAPTCHA wait
      .then((headers) => fetchPublicConfig(uid ? headers : {}))
      .then((c) => !cancelled && setConfig(c))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [attempt, ready, uid, getAuthHeaders])

  const source = useMemo(() => (config ? createApiSource({ config, getAuthHeaders }) : null), [config, getAuthHeaders])

  if (failed)
    return (
      <Splash>
        <ServerCrash className="size-8 text-fg-subtle" aria-hidden />
        <div>
          <h1 className="text-xl font-bold">PaperAid can&rsquo;t reach its server</h1>
          <p className="mt-2 max-w-md text-sm text-fg-muted">
            {import.meta.env.DEV ? (
              <>
                The backend isn&rsquo;t running. Start everything with <code className="rounded bg-surface-muted px-1.5 py-0.5">start-paperaid.bat</code> in the
                project folder, then try again.
              </>
            ) : (
              'Please check your connection and try again in a moment.'
            )}
          </p>
        </div>
        <button className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </Splash>
    )
  if (!source || !ready)
    return (
      <Splash>
        <Loader2 className="size-5 animate-spin text-brand-600" aria-label="Loading PaperAid" />
        <SlowNote />
      </Splash>
    )
  return <DataContext.Provider value={source}>{children}</DataContext.Provider>
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <DataProvider>{children}</DataProvider>
    </AuthProvider>
  )
}
