// The proposal journey against the local stack: web on :5000 and the browser-test backend on :8000
// (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles are test stand-ins.
// Usage: node scripts/e2e-proposal.mjs [screenshotDir] [proposal.docx to review]
import { mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const reviewFile = process.argv[3]
const base = 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
const problems = []
let expected = []
const expect = (...rules) => (expected = rules)
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('response', (r) => {
  if (r.status() < 400) return
  const path = new URL(r.url()).pathname
  if (!expected.some((rule) => rule.status === r.status() && rule.path.test(path))) problems.push(`unexpected ${r.status()} from ${path}`)
})
page.on('console', (m) => {
  if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) problems.push(`console: ${m.text()}`)
})
const step = (msg) => console.log(`✓ ${msg}`)
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })

async function runStep(scope) {
  await scope.getByRole('button', { name: 'See the price' }).click()
  await scope.getByRole('button', { name: 'Start' }).click()
  await page.getByText('Step finished').waitFor({ timeout: 90_000 })
}

try {
  await page.goto(`${base}/sign-in`)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app/)
  step('signed in')
  await page.goto(`${base}/admin/credits`) // payments aren't live: an admin adds test credits
  await page.getByLabel('Student email').fill('demo@paperaid.app')
  await page.getByLabel('Amount (UGX)').fill('1000000')
  await page.getByRole('button', { name: 'Add credits' }).click()
  await page.getByText(/1,000,000|1000000/).first().waitFor()
  await page.goto(`${base}/app`)

  await page.getByRole('link', { name: 'Proposals' }).first().click()
  await page.getByRole('link', { name: 'New proposal' }).click()
  await page.getByLabel('Topic').fill('Malaria vaccine uptake among caregivers of young children in Mukono District')
  await page.getByLabel('Programme').fill('Master of Public Health')
  await page.getByLabel('Faculty or school').fill('Faculty of Health Sciences')
  await page.getByLabel('Your name').fill('Grace Namukasa')
  await shot('p1-new-proposal')
  await page.getByRole('button', { name: 'Create proposal' }).click()
  await page.waitForURL(/\/app\/projects\/prj_/)
  step('project created')

  await runStep(page)
  await page.getByLabel('Title', { exact: true }).waitFor()
  await page.getByText('Only you can answer these').waitFor()
  step('plan drafted, with questions only the student can answer')
  await page.getByLabel('Accessible population (N)').fill('2400')
  await page.getByLabel('Where this figure comes from').fill('Mukono District Health Office records, 2025')
  await page.getByText(/≈ 343/).waitFor()
  step('sample size calculated from the student’s figure (343)')
  await page.getByRole('button', { name: 'Save changes' }).first().click()
  await page.getByRole('button', { name: 'Approve plan' }).click()
  await page.getByText('Approved', { exact: true }).first().waitFor()
  await shot('p2-plan-approved')
  step('plan saved and approved')

  await page.getByRole('tab', { name: /Chapter 1/ }).click()
  await runStep(page.getByRole('tabpanel'))
  await page.getByRole('heading', { name: 'General Introduction' }).waitFor()
  await page.getByText('Readiness', { exact: true }).waitFor()
  await shot('p3-chapter-one')
  step('chapter one written, with its readiness checklist')

  await page.getByRole('tab', { name: /Chapter 3/ }).click()
  await runStep(page.getByRole('tabpanel'))
  await page.getByRole('cell', { name: 'Data collection' }).waitFor()
  await page.getByText(/Yamane/).first().waitFor()
  step('chapter three written with the work-plan table and the calculated sample size')

  await page.getByRole('tab', { name: /Evidence/ }).click()
  await page.getByText('Confirmed').first().waitFor()
  await shot('p4-evidence')
  step('evidence library shows confirmed sources')

  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Draft (Word)' }).click()])
  if (!(await download.suggestedFilename()).endsWith('.docx')) throw new Error('draft download is not a Word file')
  step(`draft downloaded: ${await download.suggestedFilename()}`)
  expect({ status: 400, path: /\/export$/ })
  await page.getByRole('button', { name: 'Complete proposal' }).click()
  await page.getByText(/Before the complete proposal can be downloaded/).waitFor()
  expect()
  step('the complete proposal is refused until every chapter is written and approved')

  if (reviewFile) {
    await page.goto(`${base}/app/new?review=1`)
    await page.locator('input[type=file]').setInputFiles({ name: 'proposal.docx', mimeType: 'application/octet-stream', buffer: readFileSync(reviewFile) })
    await page.getByText(/Proposal review against the UCU manual/).waitFor({ timeout: 30_000 })
    await page.getByLabel(/This is my own work/).check()
    await page.getByRole('button', { name: /Start job/ }).click()
    await page.waitForURL(/\/app\/jobs\//)
    await page.getByRole('tab', { name: 'Proposal review' }).click({ timeout: 60_000 })
    await page.getByText('What a supervisor is likely to raise').waitFor()
    await shot('p5-review')
    step('an uploaded proposal is reviewed against the manual')
  }
} catch (e) {
  problems.push(`journey failed: ${e.message}`)
  await shot('failure')
} finally {
  await browser.close()
}
if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log('proposal journey passed')
