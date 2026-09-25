import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export interface User {
  uid: string
  email: string
  displayName: string
  isAdmin: boolean
  emailVerified: boolean
}

export interface AuthState {
  user: User | null
  ready: boolean
  mode: 'local' | 'firebase'
  signIn(email: string, password: string): Promise<void>
  signUp(email: string, password: string): Promise<void>
  signInWithGoogle(): Promise<void>
  signOut(): Promise<void>
  updateName(name: string): Promise<void>
  getAuthHeaders(): Promise<Record<string, string>>
}

const AuthContext = createContext<AuthState | null>(null)
export const FIREBASE_ENABLED = Boolean(import.meta.env.VITE_FIREBASE_API_KEY)

// --- Local mode: a developer identity the local backend accepts. Refused by production. ------

// v2: sessions saved before the fake demo sign-in was removed are dropped, so nobody stays
// signed in as demo@paperaid.app without choosing to.
const KEY = 'paperaid.local-user.v2'

function readLocal(): { email: string; displayName: string } | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as { email: string; displayName: string }) : null
  } catch {
    return null
  }
}

function writeLocal(value: { email: string; displayName: string } | null) {
  try {
    if (value) localStorage.setItem(KEY, JSON.stringify(value))
    else localStorage.removeItem(KEY)
  } catch {
    // Private mode: the session lasts until the tab closes.
  }
}

function validate(email: string, password: string) {
  if (!/^\S+@\S+\.\S+$/.test(email)) throw new Error('Enter a valid email address.')
  if (password.length < 8) throw new Error('Password must be at least 8 characters.')
}

async function whoAmI(headers: Record<string, string>): Promise<{ uid: string; isAdmin: boolean }> {
  const res = await fetch('/api/me', { headers })
  if (!res.ok) throw new Error('PaperAid is unavailable right now. Please try again shortly.')
  return (await res.json()) as { uid: string; isAdmin: boolean }
}

function LocalAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const load = useCallback(async (email: string, displayName?: string) => {
    const clean = email.trim().toLowerCase()
    const me = await whoAmI({ Authorization: `Dev ${clean}` })
    const name = displayName || clean.split('@')[0]
    writeLocal({ email: clean, displayName: name })
    setUser({ uid: me.uid, email: clean, displayName: name, isAdmin: me.isAdmin, emailVerified: true })
  }, [])

  useEffect(() => {
    const saved = readLocal()
    if (!saved) {
      setReady(true)
      return
    }
    load(saved.email, saved.displayName)
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [load])

  const email = user?.email
  const getAuthHeaders = useCallback(async (): Promise<Record<string, string>> => (email ? { Authorization: `Dev ${email}` } : {}), [email])

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      mode: 'local',
      async signIn(address, password) {
        validate(address, password)
        await load(address)
      },
      async signUp(address, password) {
        validate(address, password)
        await load(address)
      },
      async signInWithGoogle() {
        throw new Error('Google sign-in needs the Firebase project to be connected.')
      },
      async signOut() {
        writeLocal(null)
        setUser(null)
      },
      async updateName(displayName) {
        if (!user) return
        writeLocal({ email: user.email, displayName })
        setUser({ ...user, displayName })
      },
      getAuthHeaders,
    }),
    [user, ready, load, getAuthHeaders],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// --- Firebase mode ------------------------------------------------------------------------

const FIREBASE_ERRORS: Record<string, string> = {
  'auth/invalid-credential': 'Email or password is incorrect.',
  'auth/wrong-password': 'Email or password is incorrect.',
  'auth/user-not-found': 'Email or password is incorrect.',
  'auth/email-already-in-use': 'An account with this email already exists. Sign in instead.',
  'auth/weak-password': 'Choose a stronger password (at least 8 characters).',
  'auth/too-many-requests': 'Too many attempts. Please wait a minute and try again.',
  'auth/popup-closed-by-user': 'Google sign-in was closed before it finished.',
  'auth/network-request-failed': 'Check your connection and try again.',
}

function friendly(error: unknown): Error {
  const code = (error as { code?: string }).code ?? ''
  return new Error(FIREBASE_ERRORS[code] ?? 'Sign-in failed. Please try again.')
}

function FirebaseAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let unsubscribe = () => {}
    import('./firebase-client').then(({ auth, onIdTokenChanged }) => {
      unsubscribe = onIdTokenChanged(auth, async (fbUser) => {
        if (!fbUser) {
          setUser(null)
        } else {
          const token = await fbUser.getIdTokenResult()
          setUser({
            uid: fbUser.uid,
            email: fbUser.email ?? '',
            displayName: fbUser.displayName || (fbUser.email ?? '').split('@')[0],
            isAdmin: token.claims.admin === true,
            emailVerified: fbUser.emailVerified,
          })
        }
        setReady(true)
      })
    })
    return () => unsubscribe()
  }, [])

  // Stable across token refreshes: it reads the current Firebase user when called, so the data
  // layer (and any draft in progress) is not rebuilt each time the ID token refreshes.
  const getAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const fb = await import('./firebase-client')
    const current = fb.auth.currentUser
    if (!current) return {}
    const headers: Record<string, string> = { Authorization: `Bearer ${await current.getIdToken()}` }
    const appCheck = await fb.appCheckToken()
    if (appCheck) headers['X-Firebase-AppCheck'] = appCheck
    return headers
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      mode: 'firebase',
      async signIn(email, password) {
        const fb = await import('./firebase-client')
        await fb.signInWithEmailAndPassword(fb.auth, email.trim(), password).catch((e) => Promise.reject(friendly(e)))
      },
      async signUp(email, password) {
        validate(email, password)
        const fb = await import('./firebase-client')
        const cred = await fb.createUserWithEmailAndPassword(fb.auth, email.trim(), password).catch((e) => Promise.reject(friendly(e)))
        await fb.sendEmailVerification(cred.user)
      },
      async signInWithGoogle() {
        const fb = await import('./firebase-client')
        await fb.signInWithPopup(fb.auth, new fb.GoogleAuthProvider()).catch((e) => Promise.reject(friendly(e)))
      },
      async signOut() {
        const fb = await import('./firebase-client')
        await fb.signOut(fb.auth)
      },
      async updateName(displayName) {
        const fb = await import('./firebase-client')
        if (fb.auth.currentUser) await fb.updateProfile(fb.auth.currentUser, { displayName })
        setUser((u) => u && { ...u, displayName })
      },
      getAuthHeaders,
    }),
    [user, ready, getAuthHeaders],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return FIREBASE_ENABLED ? <FirebaseAuthProvider>{children}</FirebaseAuthProvider> : <LocalAuthProvider>{children}</LocalAuthProvider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
