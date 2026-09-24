import { FileQuestion } from 'lucide-react'
import { createBrowserRouter, isRouteErrorResponse, Outlet, ScrollRestoration, useRouteError } from 'react-router'
import { AppLayout } from '../components/layout/app-layout'
import { Logo } from '../components/layout/logo'
import { PublicLayout } from '../components/layout/public-layout'
import { ButtonLink } from '../components/ui/button'
import { RequireAdmin, RequireAuth, SignInPage, SignUpPage } from '../features/auth/auth-pages'
import { HomePage } from '../features/marketing/home-page'
import { FeaturesPage, PricingPage, PrivacyPage } from '../features/marketing/info-pages'

// Signed-in and admin screens load on demand, so the public site stays light on mobile data.
const lists = () => import('../features/jobs/list-pages')
const admin = () => import('../features/admin/admin-pages')

function Root() {
  return (
    <>
      <ScrollRestoration />
      <Outlet />
    </>
  )
}

function ErrorPage() {
  const error = useRouteError()
  const notFound = isRouteErrorResponse(error) && error.status === 404
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-surface-subtle px-4 text-center">
      <Logo />
      <div className="grid size-14 place-items-center rounded-full bg-brand-100 text-brand-700">
        <FileQuestion className="size-6" aria-hidden />
      </div>
      <div>
        <h1 className="text-2xl font-bold">{notFound ? 'Page not found' : 'Something went wrong'}</h1>
        <p className="mt-2 text-fg-muted">
          {notFound ? "The page you're looking for doesn't exist." : 'An unexpected error happened. Your jobs are safe — try again.'}
        </p>
      </div>
      <ButtonLink to="/">Go to home page</ButtonLink>
    </div>
  )
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    errorElement: <ErrorPage />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/features', element: <FeaturesPage /> },
          { path: '/pricing', element: <PricingPage /> },
          { path: '/privacy', element: <PrivacyPage /> },
        ],
      },
      { path: '/sign-in', element: <SignInPage /> },
      { path: '/sign-up', element: <SignUpPage /> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: '/app', lazy: () => lists().then((m) => ({ Component: m.DashboardPage })) },
              { path: '/app/new', lazy: () => import('../features/upload/new-job-page').then((m) => ({ Component: m.NewJobPage })) },
              { path: '/app/jobs/:jobId', lazy: () => import('../features/jobs/job-page').then((m) => ({ Component: m.JobPage })) },
              { path: '/app/history', lazy: () => lists().then((m) => ({ Component: m.HistoryPage })) },
              { path: '/app/credits', lazy: () => import('../features/credits/credits-page').then((m) => ({ Component: m.CreditsPage })) },
              { path: '/app/settings', lazy: () => import('../features/account/settings-page').then((m) => ({ Component: m.SettingsPage })) },
              {
                element: <RequireAdmin />,
                children: [
                  { path: '/admin', lazy: () => admin().then((m) => ({ Component: m.AdminOverviewPage })) },
                  { path: '/admin/jobs/:jobId', lazy: () => admin().then((m) => ({ Component: m.AdminJobPage })) },
                  { path: '/admin/credits', lazy: () => admin().then((m) => ({ Component: m.AdminCreditsPage })) },
                ],
              },
            ],
          },
        ],
      },
      { path: '*', element: <ErrorPage /> },
    ],
  },
])
