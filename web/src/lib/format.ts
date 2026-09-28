const ugx = new Intl.NumberFormat('en-UG', { maximumFractionDigits: 0 })

export const formatUGX = (amount: number) => `UGX ${ugx.format(amount)}`

// Students see tokens, not money (owner decision 2026-09-28). The ledger is in UGX; the rate comes
// from the server's public config and is set once when it loads.
let ugxPerToken = 1000
export const setTokenRate = (rate: number) => {
  if (rate > 0) ugxPerToken = rate
}
const tokenNumber = new Intl.NumberFormat('en', { maximumFractionDigits: 1 })
export const toTokens = (ugxAmount: number) => ugxAmount / ugxPerToken
export const formatTokenNumber = (ugxAmount: number) => tokenNumber.format(toTokens(ugxAmount))
export const formatTokens = (ugxAmount: number) => {
  const text = formatTokenNumber(ugxAmount)
  return `${text} ${text === '1' ? 'token' : 'tokens'}`
}

/** The dollar equivalent shown next to UGX amounts, at the server's configured rate. */
export const formatUSDFromUGX = (amount: number, ugxPerUsd: number) => (ugxPerUsd > 0 ? `≈ $${(amount / ugxPerUsd).toFixed(2)}` : '')

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const formatNumber = (n: number) => ugx.format(n)

const dateFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const timeFmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' })

export const formatDate = (iso: string) => dateFmt.format(new Date(iso))
export const formatDateTime = (iso: string) => `${dateFmt.format(new Date(iso))}, ${timeFmt.format(new Date(iso))}`

export function formatRelative(iso: string, now = Date.now()) {
  const diffSec = Math.round((new Date(iso).getTime() - now) / 1000)
  const abs = Math.abs(diffSec)
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (abs < 60) return rtf.format(diffSec, 'second')
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour')
  return rtf.format(Math.round(diffSec / 86400), 'day')
}

export function daysUntil(iso: string, now = Date.now()) {
  return Math.ceil((new Date(iso).getTime() - now) / 86_400_000)
}

export function formatDuration(sec: number) {
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s ? `${m}m ${s}s` : `${m}m`
}
