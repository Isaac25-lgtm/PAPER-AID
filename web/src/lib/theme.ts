import { useEffect, useLayoutEffect, useState } from 'react'

/** Day, night, or whatever the computer uses (owner, 2026-11-15). A convenience of this browser only: kept in its
 *  local storage, so it can be missing (a private window, cleared site data) and the app then shows day. */
export type Appearance = 'light' | 'dark' | 'system'

const KEY = 'paperaid.appearance'
const QUERY = '(prefers-color-scheme: dark)'

export function savedAppearance(): Appearance {
  try {
    const value = window.localStorage.getItem(KEY)
    return value === 'dark' || value === 'system' ? value : 'light'
  } catch {
    return 'light' // storage can be blocked; day is the default
  }
}

function save(value: Appearance) {
  try {
    window.localStorage.setItem(KEY, value)
  } catch {
    // storage can be blocked: the choice then lasts until the page is closed
  }
}

function resolved(value: Appearance): 'light' | 'dark' {
  return value === 'system' ? (window.matchMedia(QUERY).matches ? 'dark' : 'light') : value
}

/** The person's appearance, applied to the whole page (dialogs and menus included) while the signed-in app is open,
 *  and removed when they leave it: public pages are always day. */
export function useAppearance(): [Appearance, (value: Appearance) => void] {
  const [appearance, setAppearance] = useState<Appearance>(savedAppearance)

  useEffect(() => {
    const root = document.documentElement
    const apply = () => {
      root.dataset.theme = resolved(appearance)
    }
    apply()
    const media = window.matchMedia(QUERY)
    if (appearance === 'system') media.addEventListener('change', apply)
    return () => {
      media.removeEventListener('change', apply)
      delete root.dataset.theme
    }
  }, [appearance])

  const choose = (value: Appearance) => {
    save(value)
    setAppearance(value)
  }
  return [appearance, choose]
}

/** Pages outside the signed-in app are always day (Codex audit, 2026-11-15): the first-paint script in index.html
 *  applies night to /app and /admin before React loads, and when a signed-out visit is sent on to sign-in the app
 *  shell never mounts to take it off again. Mounted once at the router's root; inside the app the shell decides. */
export function usePublicPagesInDay(pathname: string) {
  useLayoutEffect(() => {
    if (!/^\/(app|admin)(\/|$)/.test(pathname)) delete document.documentElement.dataset.theme
  }, [pathname])
}
