import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/ui/button'
import { Dialog } from '../../components/ui/overlays'
import { Alert, Card } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { PageHero } from '../marketing/info-pages'

/** The terms people accept (owner decision 2026-10-04): plain wording until the lawyer's replaces it, as a new version. */
const TERMS = [
  { title: 'What PaperAid does', body: 'PaperAid checks, formats, writes and analyses your work for you, using its own code and AI models. You remain the author and are responsible for what you submit, and for following your institution’s and funder’s rules about AI.' },
  { title: 'Your data and your participants', body: 'You may upload only data you have the right to use: with your participants’ consent and any ethics approval your study needs. Remove names, phone numbers and ID numbers before you upload, or let PaperAid remove or leave out the columns it recognises. PaperAid can’t guarantee it finds every identifier.' },
  { title: 'What we do with it', body: 'PaperAid uses your files and data only to produce your results. Our AI providers (OpenAI, Anthropic and Google) see what a job needs, never your data’s individual records, and never use it to train their models. Files are deleted automatically after the period shown on each page, and you can delete them, or your account, at any time.' },
  { title: 'Credits', body: 'Credits are reserved when a step starts and charged only for what is delivered. A step that can’t be finished is not charged.' },
  { title: 'Changes', body: 'When these terms change, we ask you to accept the new version before your next paid step or data upload.' },
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

/** Asked when the server needs the current terms accepted (a new account by Google, or new terms). */
export function TermsDialog() {
  const data = useData()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  useEffect(() => {
    const ask = () => {
      setDone(false)
      setError(null)
      setOpen(true)
    }
    window.addEventListener('paperaid:terms', ask)
    return () => window.removeEventListener('paperaid:terms', ask)
  }, [])
  const accept = async () => {
    setBusy(true)
    setError(null)
    try {
      await data.acceptTerms(data.config.termsVersion)
      setDone(true)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={setOpen} title={done ? 'Thank you' : 'Please accept PaperAid’s terms'}
      description={done ? 'You can now try that again.' : 'Before your next paid step or data upload.'}
      footer={done ? <Button onClick={() => setOpen(false)}>Close</Button> : (
        <>
          <Button variant="secondary" onClick={() => setOpen(false)}>Not now</Button>
          <Button loading={busy} onClick={accept}>I accept</Button>
        </>
      )}>
      {!done && (
        <div className="space-y-2 text-sm text-fg-muted">
          {TERMS.slice(1, 3).map((t) => <p key={t.title}><span className="font-medium text-fg">{t.title}.</span> {t.body}</p>)}
          <p>Read the full <Link to="/terms" target="_blank" className="font-medium text-brand-700 underline">terms</Link> and the <Link to="/privacy" target="_blank" className="font-medium text-brand-700 underline">privacy summary</Link>.</p>
        </div>
      )}
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
    </Dialog>
  )
}
