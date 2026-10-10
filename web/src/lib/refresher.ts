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

/** Calls `refresh` now and then again after each `delay()`, skipping it while `hidden()`; returns what stops it.
 *  A refresh still under way when it is stopped schedules nothing afterwards: no timer outlives the page
 *  (Codex's re-audit of d4d2bc7: the next timer was set after the request came back, whatever had happened meanwhile). */
export function startPolling(refresh: () => Promise<void>, delay: () => number, hidden: () => boolean): () => void {
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const tick = async () => {
    if (disposed) return
    if (!hidden()) await refresh()
    if (disposed) return
    timer = setTimeout(tick, delay())
  }
  void tick()
  return () => {
    disposed = true
    if (timer !== undefined) clearTimeout(timer)
  }
}
