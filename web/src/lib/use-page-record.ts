import { useCallback, useEffect, useState } from 'react'
import { DataError } from './data'
import { recordLoader } from './record-loader'

/** Used inside a component keyed by its route ID, so navigation also resets local workspace state. */
export function usePageRecord<T extends { id: string; updatedAt: string }>(id: string, read: () => Promise<T | null>, failure: string) {
  const [record, setRecord] = useState<T | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [loader] = useState(() => recordLoader<T>(id, (value) => {
    setRecord(value)
    setError(null)
  }, (e) => setError(e instanceof DataError ? e.message : failure)))
  const load = useCallback(() => { void loader.load(read) }, [loader, read])
  useEffect(() => {
    loader.activate()
    load()
    return () => loader.deactivate()
  }, [loader, load])
  return { record, error, load, change: loader.apply }
}
