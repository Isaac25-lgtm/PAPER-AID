import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Dialog } from '../../components/ui/overlays'
import { Alert, Card } from '../../components/ui/primitives'
import type { TermsAsk } from '../../lib/api-source'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { PageHero } from '../marketing/info-pages'

/** The terms people accept (owner decision 2026-10-04): plain wording until the lawyer's replaces it, as a new version. */
const TERMS = [
  { title: 'What PaperAid does', body: 'PaperAid checks, formats and writes your work for you, using its own code and AI models. You remain the author and are responsible for what you submit, and for following your institution’s and funder’s rules about AI.' },
  { title: 'What you upload', body: 'You may upload only files you have the right to use. Leave out your participants’ names, phone numbers and ID numbers.' },
  { title: 'What we do with it', body: 'PaperAid uses your files only to produce your results. The AI service PaperAid uses sees only what each step needs, and never uses any of it to train its models. Files are deleted automatically after the period shown on each page, and you can delete them, or your account, at any time.' },
  { title: 'Credits', body: 'Credits are reserved when a step starts and charged only for what is delivered. A step that can’t be finished is not charged.' },
  { title: 'Changes', body: 'When these terms change, we ask you to accept the new version before your next paid step.' },
]

export function TermsPage() {
  useTitle('Terms')
  const { config } = useData()
  return (
    <>
      <PageHero eyebrow="Terms" title="The terms of using PaperAid, in plain words.">
        Version {config.termsVersion}. Read them with the <Link to="/privacy" className="font-medium text-brand-700 underline">privacy summary</Link>.
      </PageHero>
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-14 sm:px-6">
        {TERMS.map((t) => (
          <Card key={t.title} className="p-6">
            <h2 className="text-lg font-semibold">{t.title}</h2>
            <p className="mt-2 leading-relaxed text-fg-muted">{t.body}</p>
          </Card>
        ))}
      </div>
    </>
  )
}

/** The points a person agrees to before PaperAid handles anything of theirs (owner, 2026-11-17, as PaperAid Pro does):
 *  the same three, ticked one by one, wherever they are asked (Codex audit 2026-11-17: one flow, not a one-click prompt). */
const POINTS = [
  { id: 'terms', text: <>I accept the <Link to="/terms" target="_blank" className="font-medium text-brand-700 underline">terms of using PaperAid</Link>.</> },
  { id: 'privacy', text: <>I have read the <Link to="/privacy" target="_blank" className="font-medium text-brand-700 underline">privacy summary</Link>.</> },
  { id: 'ai', text: <>PaperAid uses AI to research, write and check. I remain the author, responsible for what I submit and for following my institution&rsquo;s or funder&rsquo;s rules about AI.</> },
]

function useConsent(version: string | null, onAccepted: () => void) {
  const data = useData()
  const [ticked, setTicked] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ready = POINTS.every((p) => ticked[p.id]) && version !== null
  const agree = async () => {
    if (!version) return
    setBusy(true)
    setError(null)
    try {
      await data.acceptTerms(version) // the version the server says is current, never the one the page loaded with
      setTicked({})
      onAccepted()
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }
  const points = (
    <ul className="space-y-3">
      {POINTS.map((p) => (
        <li key={p.id}>
          <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line-strong p-3 text-sm leading-relaxed text-fg hover:bg-surface-subtle">
            <input type="checkbox" className="mt-1 size-4 shrink-0 accent-[var(--color-brand-600)]" checked={Boolean(ticked[p.id])}
              onChange={(e) => setTicked({ ...ticked, [p.id]: e.target.checked })} />
            <span>{p.text}</span>
          </label>
        </li>
      ))}
    </ul>
  )
  return { points, ready, busy, error, agree }
}

/** Shown instead of the page an account opened until it has accepted the current terms (owner, 2026-11-17). */
export function ConsentGate({ version, onAccepted }: { version: string; onAccepted: () => void }) {
  useTitle('Before you start')
  const consent = useConsent(version, onAccepted)
  return (
    <div className="mx-auto max-w-xl py-6">
      <Card className="p-6 sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Before you start</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">Please read and agree to how PaperAid works. Version {version}.</p>
        <div className="mt-6">{consent.points}</div>
        {consent.error && <Alert tone="danger" className="mt-4">{consent.error}</Alert>}
        <Button className="mt-6 w-full" disabled={!consent.ready} loading={consent.busy} onClick={consent.agree}>Agree and continue</Button>
      </Card>
    </div>
  )
}

/** Asked when a step meets terms that changed while the tab was open (the server answered TERMS_REQUIRED): the same
 *  points as the gate, for the version the server holds now; the step carries on once they are accepted. */
export function TermsDialog() {
  const data = useData()
  const [open, setOpen] = useState(false)
  const [version, setVersion] = useState<string | null>(null)
  const waiting = useRef<TermsAsk['resolve'][]>([])
  const settle = (accepted: boolean) => {
    for (const resolve of waiting.current.splice(0)) resolve(accepted)
  }
  useEffect(() => {
    const ask = (event: Event) => {
      event.preventDefault() // claimed: the step waits for the answer here
      const detail = (event as CustomEvent<TermsAsk | null>).detail
      if (detail) waiting.current.push(detail.resolve)
      setVersion(null)
      setOpen(true)
      data.preferences().then((p) => setVersion(p.termsVersion)).catch(() => setVersion(data.config.termsVersion)) // the server refuses a stale one
    }
    window.addEventListener('paperaid:terms', ask)
    return () => {
      window.removeEventListener('paperaid:terms', ask)
      settle(false)
    }
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps
  const close = (next: boolean) => {
    setOpen(next)
    if (!next) settle(false)
  }
  const consent = useConsent(version, () => {
    setOpen(false)
    settle(true)
  })
  return (
    <Dialog open={open} onOpenChange={close} title="Please accept PaperAid’s terms" description={`PaperAid’s terms changed${version ? ` (version ${version})` : ''}. Your step carries on as soon as you accept.`}
      footer={(
        <>
          <Button variant="secondary" onClick={() => close(false)}>Not now</Button>
          <Button disabled={!consent.ready} loading={consent.busy} onClick={consent.agree}>Agree and continue</Button>
        </>
      )}>
      {consent.points}
      {consent.error && <Alert tone="danger" className="mt-3">{consent.error}</Alert>}
    </Dialog>
  )
}
