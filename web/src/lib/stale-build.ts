/**
 * After a deploy, a tab still running the previous version asks for page files that no longer
 * exist, and the host answers with the site's HTML. Reload once to fetch the new version instead of
 * showing an error; a second failure soon after is a real error and is shown.
 */
const KEY = 'paperaid:reloaded-for-update'
const WINDOW_MS = 30_000

/** Whether an error is a page file that failed to load (Chrome, Firefox and Safari wordings). */
export function isStaleBuildError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  return /dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(message)
}

/** Reloads the page unless it already reloaded for an update moments ago; true when reloading. */
export function reloadForUpdate(now = Date.now()): boolean {
  try {
    if (now - Number(sessionStorage.getItem(KEY) ?? 0) < WINDOW_MS) return false
    sessionStorage.setItem(KEY, String(now))
  } catch (error) {
    if (error instanceof DOMException) return false // storage blocked: never risk a reload loop
    throw error
  }
  window.location.reload()
  return true
}
