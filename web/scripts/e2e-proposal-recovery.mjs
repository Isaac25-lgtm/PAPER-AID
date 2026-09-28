// Regression journey for Codex's browser findings (audit 2026-09-28 #9 and #15), against the local
// test stack: web on :5000 and the browser-test backend on :8000 (python -m tests.serve_e2e).
// Asserts the correct behaviour: a stale plan edit is refused and shown as a conflict, a failed
// load shows its error with a retry, and refused step monitoring is shown instead of "Queued".
// Usage: node scripts/e2e-proposal-recovery.mjs
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const base = 'http://localhost:5000'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext()
const page = await context.newPage()
const headers = { Authorization: 'Dev demo@paperaid.app' }
const api = async (path, data, expected = 200) => {
  const res = data === undefined ? await context.request.get(base + path, { headers }) : await context.request.post(base + path, { headers, data })
  assert.equal(res.status(), expected, await res.text())
  return res.json()
}
const step = (msg) => console.log(`✓ ${msg}`)

try {
  await api('/api/wallet') // the account opens its wallet (as signing in does) before credits can be granted
  await api('/api/admin/credits', { email: 'demo@paperaid.app', amount: 1000000, note: 'recovery journey', opId: `recovery-${Date.now()}` })
  await page.goto(`${base}/sign-in`)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app/)
  const project = await api('/api/projects', { inputs: { topic: 'Malaria vaccine uptake in Mukono District', level: 'MASTERS', programme: 'Master of Public Health' } })
  const quoted = await api(`/api/projects/${project.id}/steps`, { step: 'PLAN' })
  await api(`/api/projects/${project.id}/steps/${quoted.job.id}/submit`, { quoteId: quoted.quote.id })
  for (let i = 0; i < 200 && (await api(`/api/jobs/${quoted.job.id}`)).status !== 'COMPLETED'; i++) await new Promise((r) => setTimeout(r, 100))

  // 9 — a dirty editor meets a newer saved plan: shown as a conflict, and its save is refused.
  // The page refreshes its project when the step finishes, while the local edit is still unsaved.
  await page.goto(`${base}/app/projects/${project.id}`)
  await page.getByLabel('Title', { exact: true }).fill('My unsaved title edit')
  await page.getByRole('button', { name: 'See the price', exact: true }).click()
  await page.route('**/api/projects/*/steps/*/submit', async (route) => {
    const response = await route.fetch()
    const current = await api(`/api/projects/${project.id}`)
    await api(`/api/projects/${project.id}/plan`, { baseVersion: current.planVersion, plan: { ...current.plan, problem: 'A new problem saved elsewhere must be preserved.' } })
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.getByText('Step finished', { exact: true }).waitFor({ timeout: 60000 })
  await page.getByText('Your plan changed elsewhere').waitFor()
  await page.getByRole('button', { name: 'Save changes' }).first().click()
  await page.getByText(/changed elsewhere \(another tab/).waitFor() // the server's refusal
  const kept = await api(`/api/projects/${project.id}`)
  assert.equal(kept.plan.problem, 'A new problem saved elsewhere must be preserved.')
  assert.notEqual(kept.plan.title, 'My unsaved title edit')
  step('a stale plan edit is refused and shown as a conflict; the newer plan is kept')

  // 15a — a failed project load shows its error and a retry, not an endless skeleton.
  const loadPage = await context.newPage()
  await loadPage.route(`**/api/projects/${project.id}`, (r) => r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'PROJECT_LOAD_FAILURE' }) }))
  await loadPage.goto(`${base}/app/projects/${project.id}`)
  await loadPage.getByText('PROJECT_LOAD_FAILURE').waitFor()
  await loadPage.getByRole('button', { name: 'Try again' }).waitFor()
  step('a failed load shows its error with a retry')

  // 15b — refused step monitoring is shown, with a way to check again.
  const progressPage = await context.newPage()
  await progressPage.route(`**/api/projects/${project.id}`, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...kept, activeJob: 'job_blocked' }) }))
  await progressPage.route('**/api/jobs/job_blocked', (r) => r.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ message: 'APPCHECK_UNAVAILABLE' }) }))
  await progressPage.goto(`${base}/app/projects/${project.id}`)
  await progressPage.getByText('We lost track of this step').waitFor()
  await progressPage.getByText(/APPCHECK_UNAVAILABLE/).waitFor()
  await progressPage.getByRole('button', { name: 'Check again' }).waitFor()
  step('refused monitoring is shown with a way to check again')
  console.log('recovery journey passed')
} finally {
  await browser.close()
}
