import { useCallback, useEffect, useState } from 'react'
import { DataError, useData } from './data'
import type { Wallet } from './types'

const WALLET_CHANGED = 'paperaid:wallet-changed'

/** Tell every mounted balance (header chip, credits page, price panel) to refresh. */
export function walletChanged() {
  window.dispatchEvent(new Event(WALLET_CHANGED))
}

/** The signed-in student's credits, kept fresh whenever something moves them. */
export function useWallet() {
  const data = useData()
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setWallet(await data.getWallet())
      setError(null)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'We could not load your credits.')
    }
  }, [data])

  useEffect(() => {
    refresh()
    window.addEventListener(WALLET_CHANGED, refresh)
    return () => window.removeEventListener(WALLET_CHANGED, refresh)
  }, [refresh])

  return { wallet, error, refresh }
}
