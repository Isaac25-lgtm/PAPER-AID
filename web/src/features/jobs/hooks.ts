import { useCallback, useEffect, useState } from 'react'
import { DataError, useData, type JobQuery } from '../../lib/data'
import type { Job } from '../../lib/types'

export function useJob(jobId: string) {
  const data = useData()
  const [state, setState] = useState<{ job: Job | null; loading: boolean }>({ job: null, loading: true })

  useEffect(() => {
    setState({ job: null, loading: true })
    return data.watchJob(jobId, (job) => setState({ job, loading: false }))
  }, [data, jobId])

  return state
}

export function useJobList(query: Omit<JobQuery, 'cursor'>) {
  const data = useData()
  const [jobs, setJobs] = useState<Job[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const key = JSON.stringify(query)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    data
      .listJobs(JSON.parse(key) as JobQuery)
      .then((page) => {
        if (cancelled) return
        setJobs(page.items)
        setCursor(page.nextCursor)
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof DataError ? e.message : 'We could not load your jobs.'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [data, key])

  const loadMore = useCallback(async () => {
    if (!cursor) return
    setLoadingMore(true)
    try {
      const page = await data.listJobs({ ...(JSON.parse(key) as JobQuery), cursor })
      setJobs((prev) => [...prev, ...page.items])
      setCursor(page.nextCursor)
    } finally {
      setLoadingMore(false)
    }
  }, [data, key, cursor])

  return { jobs, loading, loadingMore, error, hasMore: cursor !== null, loadMore }
}
