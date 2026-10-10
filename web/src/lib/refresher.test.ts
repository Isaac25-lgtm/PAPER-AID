import { describe, expect, it } from 'vitest'
import { createRefresher } from './refresher'

/** A load whose answers the test releases by hand, in any order. */
function manual<T>() {
  const pending: { resolve: (value: T) => void; reject: (error: Error) => void }[] = []
  const load = () => new Promise<T>((resolve, reject) => pending.push({ resolve, reject }))
  return { load, pending }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('createRefresher', () => {
  it('keeps what was last loaded when a refresh fails, and says the refresh failed', async () => {
    const { load, pending } = manual<string[]>()
    const seen: string[][] = []
    const failures: boolean[] = []
    const refresher = createRefresher(load, (data) => seen.push(data), (failed) => failures.push(failed))

    void refresher.refresh()
    pending[0].resolve(['essay'])
    await settle()
    void refresher.refresh()
    pending[1].reject(new Error('the list request failed'))
    await settle()

    expect(seen).toEqual([['essay']]) // never replaced by an empty list
    expect(failures).toEqual([false, true])
  })

  it('never lets an older answer replace a newer one: one request at a time', async () => {
    const { load, pending } = manual<string>()
    const seen: string[] = []
    const refresher = createRefresher(load, (data) => seen.push(data), () => {})

    void refresher.refresh() // the slow one
    void refresher.refresh() // asked while it is under way: skipped, not sent
    expect(pending).toHaveLength(1)
    pending[0].resolve('Writing…')
    await settle()
    void refresher.refresh()
    pending[1].resolve('Ready')
    await settle()

    expect(seen).toEqual(['Writing…', 'Ready']) // in the order they were asked for
  })

  it('delivers nothing that arrives after it was stopped', async () => {
    const { load, pending } = manual<string>()
    const seen: string[] = []
    const failures: boolean[] = []
    const refresher = createRefresher(load, (data) => seen.push(data), (failed) => failures.push(failed))

    void refresher.refresh()
    refresher.stop() // the page was left, or the data source changed
    pending[0].resolve('from the old source')
    await settle()
    void refresher.refresh()

    expect(seen).toEqual([])
    expect(failures).toEqual([])
    expect(pending).toHaveLength(1)
  })
})
