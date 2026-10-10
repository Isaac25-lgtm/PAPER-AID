/** Keeps one list fresh by asking for it again and again, safely (Codex's audit of cbb99cb, findings 7 and 8).
 *
 *  - One request at a time: a refresh asked for while another is under way is skipped, so a slow, older answer can
 *    never arrive after a newer one and put back what was true before.
 *  - A failed refresh changes nothing: what was last loaded stays, and the caller is told the refresh failed.
 *  - After `stop()` (the page left, or the source changed) nothing that arrives late is delivered. */
export interface Refresher {
  refresh(): Promise<void>
  stop(): void
}

export function createRefresher<T>(load: () => Promise<T>, onData: (data: T) => void, onFailure: (failed: boolean) => void): Refresher {
  let inFlight = false
  let stopped = false
  return {
    async refresh() {
      if (inFlight || stopped) return
      inFlight = true
      try {
        const data = await load()
        if (!stopped) {
          onData(data)
          onFailure(false)
        }
      } catch {
        if (!stopped) onFailure(true)
      } finally {
        inFlight = false
      }
    },
    stop() {
      stopped = true
    },
  }
}
