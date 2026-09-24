import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/field'
import { Dialog } from '../../components/ui/overlays'
import { Alert, Card, PageHeader } from '../../components/ui/primitives'
import { DataError, useData } from '../../lib/data'
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
