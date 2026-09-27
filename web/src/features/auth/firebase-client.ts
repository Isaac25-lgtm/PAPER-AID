// Loaded only when VITE_FIREBASE_API_KEY is set, so local builds never pull in the Firebase SDK.
import { initializeApp } from 'firebase/app'
import { getToken, initializeAppCheck, ReCaptchaEnterpriseProvider } from 'firebase/app-check'
import { getAuth } from 'firebase/auth'

const env = import.meta.env
const app = initializeApp({
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  appId: env.VITE_FIREBASE_APP_ID,
})

export const auth = getAuth(app)

const appCheck = env.VITE_APPCHECK_SITE_KEY
  ? initializeAppCheck(app, { provider: new ReCaptchaEnterpriseProvider(env.VITE_APPCHECK_SITE_KEY), isTokenAutoRefreshEnabled: true })
  : null

/** The App Check token for the next request, or null when none could be obtained (for example when
 *  reCAPTCHA is throttling this browser). The request then goes out without one and the server
 *  answers with its clear "could not be verified, refresh the page" message instead of the browser
 *  reporting a connection failure. */
export async function appCheckToken(): Promise<string | null> {
  if (!appCheck) return null
  return getToken(appCheck).then(
    (result) => result.token,
    () => null,
  )
}

export {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  onIdTokenChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
} from 'firebase/auth'
