import { describe, expect, it, vi } from 'vitest'
import { recordLoader } from './record-loader'

type Record = { id: string; updatedAt: string; version: number }
const record = (version: number, id = 'work-a'): Record => ({ id, version, updatedAt: `2026-10-08T10:00:0${version}.000000Z` })
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

describe('work and project response ordering', () => {
  it('still makes progress when requests take longer than the polling interval', async () => {
    const show = vi.fn()
    const page = recordLoader<Record>('work-a', show, vi.fn())
    page.activate()
    const first = deferred<Record>(), second = deferred<Record>()
    const a = page.load(() => first.promise), b = page.load(() => second.promise)
    first.resolve(record(1)); await a
    expect(show).toHaveBeenLastCalledWith(record(1))
    second.resolve(record(2)); await b
    expect(show).toHaveBeenLastCalledWith(record(2))
  })

  it('keeps the newer poll when responses arrive in reverse order', async () => {
    const show = vi.fn(), fail = vi.fn()
    const page = recordLoader<Record>('work-a', show, fail)
    page.activate()
    const old = deferred<Record>(), next = deferred<Record>()
    const a = page.load(() => old.promise), b = page.load(() => next.promise)
    next.resolve(record(2)); await b
    old.resolve(record(1)); await a
    expect(show.mock.calls).toEqual([[record(2)]])
    expect(fail).not.toHaveBeenCalled()
  })

  it('ignores old errors and responses after navigating away', async () => {
    const show = vi.fn(), fail = vi.fn()
    const page = recordLoader<Record>('work-a', show, fail)
    page.activate()
    const old = deferred<Record>(), next = deferred<Record>()
    const a = page.load(() => old.promise), b = page.load(() => next.promise)
    next.resolve(record(2)); await b
    old.reject(new Error('stale error')); await a
    const late = deferred<Record>(), pending = page.load(() => late.promise)
    page.deactivate()
    late.resolve(record(3)); await pending
    const read = vi.fn(async () => record(4))
    await page.load(read)
    expect(read).not.toHaveBeenCalled()
    expect(show.mock.calls).toEqual([[record(2)]])
    expect(fail).not.toHaveBeenCalled()
  })

  it('a saved change supersedes outstanding polls and older mutation responses', async () => {
    const show = vi.fn()
    const page = recordLoader<Record>('work-a', show, vi.fn())
    page.activate()
    const old = deferred<Record>(), pending = page.load(() => old.promise)
    page.apply(record(3))
    old.resolve(record(1)); await pending
    page.apply(record(2))
    page.apply(record(4, 'work-b'))
    expect(show.mock.calls).toEqual([[record(3)]])
  })

  it('compares microseconds and discards a request from before effect cleanup', async () => {
    const show = vi.fn()
    const page = recordLoader<Record>('work-a', show, vi.fn())
    page.activate()
    const old = deferred<Record>(), pending = page.load(() => old.promise)
    page.deactivate(); page.activate()
    const newest = { ...record(3), updatedAt: '2026-10-08T10:00:00.000002Z' }
    page.apply(newest)
    page.apply({ ...record(2), updatedAt: '2026-10-08T10:00:00.000001Z' })
    old.resolve(record(4)); await pending
    expect(show.mock.calls).toEqual([[newest]])
  })
})
