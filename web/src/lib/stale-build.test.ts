import { afterEach, describe, expect, it, vi } from 'vitest'
import { isStaleBuildError, reloadForUpdate } from './stale-build'

describe('stale build recovery', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('recognises a page file that failed to load in each browser', () => {
    expect(isStaleBuildError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/job-page-abc.js'))).toBe(true)
    expect(isStaleBuildError(new TypeError('error loading dynamically imported module'))).toBe(true)
    expect(isStaleBuildError(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isStaleBuildError(new Error('Request failed'))).toBe(false)
    expect(isStaleBuildError(null)).toBe(false)
  })

  it('reloads once, then shows the error instead of looping', () => {
    const store = new Map<string, string>()
    vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) })
    const reload = vi.fn()
    vi.stubGlobal('window', { location: { reload } })

    expect(reloadForUpdate(100_000)).toBe(true)
    expect(reloadForUpdate(110_000)).toBe(false)
    expect(reloadForUpdate(200_000)).toBe(true)
    expect(reload).toHaveBeenCalledTimes(2)
  })

  it('never reloads when storage is blocked', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw new DOMException('blocked', 'SecurityError') } })
    const reload = vi.fn()
    vi.stubGlobal('window', { location: { reload } })

    expect(reloadForUpdate()).toBe(false)
    expect(reload).not.toHaveBeenCalled()
  })
})
