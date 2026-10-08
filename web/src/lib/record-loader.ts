type RecordStamp = { id: string; updatedAt: string }

function older(a: string, b: string): boolean {
  const diff = Date.parse(a) - Date.parse(b)
  if (diff !== 0) return diff < 0
  // The API preserves microseconds; Date.parse alone rounds those away.
  const fraction = (s: string) => (s.match(/\.(\d+)(?:Z|[+-]\d\d:\d\d)$/)?.[1] ?? '').padEnd(9, '0')
  return fraction(a) < fraction(b)
}

/** Ordering for one mounted work/project page, shared by polling and mutation responses. */
export function recordLoader<T extends RecordStamp>(id: string, show: (value: T | null) => void, fail: (error: unknown) => void) {
  let active = false
  let generation = 0
  let requested = 0
  let displayed = 0
  let latest: T | null = null
  const publish = (value: T | null) => {
    if (!active || (value && (value.id !== id || (latest && older(value.updatedAt, latest.updatedAt))))) return false
    latest = value
    show(value)
    return true
  }
  return {
    activate() { active = true },
    deactivate() { active = false; generation++ },
    async load(read: () => Promise<T | null>) {
      if (!active) return
      const request = ++requested
      const startedIn = generation
      try {
        const value = await read()
        // Accept useful progress even while a newer poll is pending. Otherwise a connection slower
        // than the polling interval would continually invalidate every response and never update.
        if (active && startedIn === generation && request > displayed && publish(value)) displayed = request
      } catch (error) {
        if (active && startedIn === generation && request === requested) fail(error)
      }
    },
    apply(value: T) {
      if (publish(value)) generation++ // a response saved by the server supersedes outstanding polls
    },
  }
}
