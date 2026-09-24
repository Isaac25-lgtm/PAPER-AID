import { clsx } from 'clsx'
import { ArrowDownLeft, ArrowUpRight, Lock, Smartphone, Wallet as WalletIcon } from 'lucide-react'
import { Link } from 'react-router'
import { Alert, Badge, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui/primitives'
import { useData } from '../../lib/data'
import { formatDateTime, formatUGX, formatUSDFromUGX } from '../../lib/format'
import type { LedgerEntry } from '../../lib/types'
import { useTitle } from '../../lib/use-title'
import { useWallet } from '../../lib/use-wallet'

const KIND_LABELS: Record<LedgerEntry['kind'], string> = {
  TOP_UP: 'Credits added',
  HOLD: 'Held',
  CHARGE: 'Charged',
  RELEASE: 'Returned',
  REFUND: 'Refunded',
}

// Money coming back to the available balance shows as positive; money leaving it as negative.
const SIGN: Record<LedgerEntry['kind'], 1 | -1 | 0> = { TOP_UP: 1, HOLD: -1, CHARGE: 0, RELEASE: 1, REFUND: 1 }

export function CreditsPage() {
  useTitle('Credits')
  const { config } = useData()
  const { wallet, error } = useWallet()
  const rate = wallet?.ugxPerUsd ?? config.ugxPerUsd

  return (
    <>
      <PageHeader title="Credits" description="You pay for the work each paper needs, from credits you add in advance. Credits never expire." />
      {error && (
        <Alert tone="danger" className="mb-5">
          {error}
        </Alert>
      )}
      {wallet?.testCredits && (
        <Alert tone="warning" className="mb-5" title="Test credits">
          This is a local test setup. These credits are added by an admin for testing and are not money.
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5 md:col-span-2">
          <p className="flex items-center gap-2 text-sm font-medium text-fg-muted">
            <WalletIcon className="size-4 text-brand-600" aria-hidden /> Available
          </p>
          {wallet ? (
            <p className="mt-2 flex flex-wrap items-baseline gap-x-3 text-4xl font-bold tracking-tight">
              {formatUGX(wallet.available)} <span className="text-base font-medium text-fg-subtle">{formatUSDFromUGX(wallet.available, rate)}</span>
            </p>
          ) : (
            <Skeleton className="mt-3 h-10 w-56" />
          )}
          {wallet && wallet.held > 0 && (
            <p className="mt-3 flex items-center gap-2 text-sm text-fg-muted">
              <Lock className="size-4 text-amber-600" aria-hidden /> {formatUGX(wallet.held)} held for work in progress. Whatever a job doesn&rsquo;t use comes back here.
            </p>
          )}
        </Card>
        <Card className="p-5">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Smartphone className="size-4 text-brand-600" aria-hidden /> Add credits
          </p>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">
            Top-ups with mobile money open soon, from {formatUGX(config.minTopUpUgx)} ({formatUSDFromUGX(config.minTopUpUgx, rate)}).
          </p>
          <p className="mt-3 text-xs text-fg-subtle">Until then, PaperAid adds credits for you. Credits can&rsquo;t be withdrawn as cash.</p>
        </Card>
      </div>

      <h2 className="mt-10 mb-3 text-base font-semibold">History</h2>
      {!wallet ? (
        <Skeleton className="h-40 w-full" />
      ) : wallet.entries.length === 0 ? (
        <EmptyState icon={<WalletIcon className="size-5" aria-hidden />} title="No activity yet">
          Credits you add, estimates and jobs will appear here.
        </EmptyState>
      ) : (
        <Card className="divide-y divide-line">
          {wallet.entries.map((e) => {
            const sign = SIGN[e.kind]
            return (
              <div key={e.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
                <span className={clsx('grid size-8 shrink-0 place-items-center rounded-full', sign > 0 ? 'bg-brand-50 text-brand-700' : 'bg-surface-muted text-fg-muted')}>
                  {sign > 0 ? <ArrowDownLeft className="size-4" aria-hidden /> : <ArrowUpRight className="size-4" aria-hidden />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {KIND_LABELS[e.kind]} <span className="font-normal text-fg-muted">· {e.note}</span>
                  </p>
                  <p className="text-xs text-fg-subtle">
                    {formatDateTime(e.at)}
                    {e.jobId && (
                      <>
                        {' · '}
                        <Link to={`/app/jobs/${e.jobId}`} className="underline-offset-2 hover:underline">
                          {e.jobId}
                        </Link>
                      </>
                    )}
                  </p>
                </div>
                <div className="text-right">
                  <p className={clsx('font-semibold', sign > 0 && 'text-brand-700')}>
                    {sign > 0 ? '+' : sign < 0 ? '−' : ''}
                    {formatUGX(e.amount)}
                  </p>
                  <p className="text-xs text-fg-subtle">Balance {formatUGX(e.availableAfter)}</p>
                </div>
                {e.kind === 'CHARGE' && <Badge className="sm:ml-2">from hold</Badge>}
              </div>
            )
          })}
        </Card>
      )}
    </>
  )
}
