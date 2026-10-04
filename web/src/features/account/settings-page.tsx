import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button } from '../../components/ui/button'
import { Checkbox, Input } from '../../components/ui/field'
import { Dialog } from '../../components/ui/overlays'
import { Alert, Card, PageHeader } from '../../components/ui/primitives'
import { DataError, useData, type Notifications } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { useAuth } from '../auth/auth-context'

export function SettingsPage() {
  useTitle('Settings')
  const { user, updateName, signOut } = useAuth()
  const data = useData()
  const { config } = data
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const navigate = useNavigate()
  const [name, setName] = useState(user?.displayName ?? '')
  const [saved, setSaved] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  return (
    <div className="max-w-2xl">
      <PageHeader title="Settings" />
      <div className="space-y-5">
        <Card className="p-6">
          <h2 className="text-base font-semibold">Profile</h2>
          <form
            className="mt-4 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updateName(name.trim() || (user?.displayName ?? '')).then(() => setSaved(true))
            }}
          >
            <Input label="Display name" value={name} onChange={(e) => (setName(e.target.value), setSaved(false))} autoComplete="name" />
            <Input label="Email" value={user?.email ?? ''} disabled hint="Your sign-in email can't be changed here." />
            <div className="flex items-center gap-3">
              <Button type="submit" variant="secondary">
                Save
              </Button>
              {saved && (
                <span role="status" className="text-sm text-brand-700">
                  Saved
                </span>
              )}
            </div>
          </form>
        </Card>

        <NotificationsCard />

        <Card className="p-6">
          <h2 className="text-base font-semibold">Your files</h2>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">
            Uploaded papers and results are deleted automatically {config.retentionDays} days after each job. You can delete any finished job sooner from
            its page. See the{' '}
            <Link to="/privacy" className="font-medium text-brand-700 underline">
              privacy summary
            </Link>{' '}
            for details.
          </p>
        </Card>

        <Card className="border-red-200 p-6">
          <h2 className="text-base font-semibold text-red-800">Delete account</h2>
          <p className="mt-2 text-sm text-fg-muted">Deletes your account, every job and every file. If a job is being processed, wait for it to finish first. This can&rsquo;t be undone.</p>
          <Button variant="danger" className="mt-4" onClick={() => setConfirmOpen(true)}>
            Delete my account
          </Button>
        </Card>
      </div>

      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete your account?"
        description="All your papers, results and reports will be permanently deleted."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={confirmText !== 'DELETE'}
              loading={deleting}
              onClick={async () => {
                setDeleting(true)
                setDeleteError(null)
                try {
                  await data.deleteAccount()
                  await signOut()
                  navigate('/')
                } catch (e) {
                  setDeleteError(e instanceof DataError ? e.message : 'We could not delete your account. Try again.')
                  setDeleting(false)
                }
              }}
            >
              Delete account
            </Button>
          </>
        }
      >
        <Input label='Type "DELETE" to confirm' value={confirmText} onChange={(e) => setConfirmText(e.target.value)} autoComplete="off" />
        {deleteError && (
          <Alert tone="danger" className="mt-3">
            {deleteError}
          </Alert>
        )}
      </Dialog>
    </div>
  )
}

/** "Your work is ready" messages. Shown only when PaperAid can send email or texts. */
function NotificationsCard() {
  const data = useData()
  const [choice, setChoice] = useState<Notifications | null>(null)
  const [phone, setPhone] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  useEffect(() => {
    data
      .notifications()
      .then((n) => (setChoice(n), setPhone(n.phone)))
      .catch((e: unknown) => setError(e instanceof DataError ? e.message : 'Could not load your message settings.'))
  }, [data])

  if (error && !choice) return null // the rest of the page works without this card
  if (!choice || !(choice.available.email || choice.available.sms)) return null

  async function save(next: Partial<Omit<Notifications, 'available'>>) {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const n = await data.setNotifications(next)
      setChoice(n)
      setPhone(n.phone)
      setSaved(true)
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">Messages</h2>
      <p className="mt-2 text-sm text-fg-muted">We tell you when your work is ready, or if it stops. Messages never include your text.</p>
      <div className="mt-4 space-y-4">
        {choice.available.email && (
          <Checkbox label="Email me" checked={choice.notifyEmail} disabled={saving} onChange={(e) => save({ notifyEmail: e.target.checked })} />
        )}
        {choice.available.sms && (
          <>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                save({ phone: phone.trim() })
              }}
            >
              <Input
                label="Phone number"
                className="min-w-0 flex-1"
                type="tel"
                value={phone}
                placeholder="+256 7XX XXX XXX"
                autoComplete="tel"
                onChange={(e) => (setPhone(e.target.value), setSaved(false))}
              />
              <Button type="submit" variant="secondary" loading={saving} disabled={phone.trim() === choice.phone}>
                Save number
              </Button>
            </form>
            <Checkbox
              label="Text me"
              checked={choice.notifySms}
              disabled={saving || !choice.phone}
              onChange={(e) => save({ notifySms: e.target.checked })}
            />
          </>
        )}
        {saved && (
          <p role="status" className="text-sm text-brand-700">
            Saved
          </p>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Card>
  )
}
