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
  await page.getByLabel('Amount (tokens)').fill('1000')
  await page.getByRole('button', { name: 'Add credits' }).click()
  await page.getByText(/Their balance is now/).first().waitFor()
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

  await page.getByRole('button', { name: 'See the price' }).click()
  await page.getByText('Plan and Chapter One together').waitFor()
  await page.getByRole('button', { name: 'Start' }).click()
  await page.getByText('Step finished').waitFor({ timeout: 90_000 })
  await page.getByLabel('Title', { exact: true }).waitFor()
  await page.getByText('Only you can answer these').waitFor()
  step('plan drafted, with questions only the student can answer')
  await page.getByText('The research gap').waitFor()
  await page.getByText('Rests on one confirmed source').waitFor()
  await page.getByText('Distance was associated with lower uptake', { exact: false }).first().waitFor()
  step('the research gap is built from confirmed evidence and shows its source')
  await page.getByLabel('Accessible population (N)').fill('2400')
  await page.getByLabel('Where this figure comes from').fill('Mukono District Health Office records, 2025')
  await page.getByText(/≈ 343/).waitFor()
  step('sample size calculated from the student’s figure (343)')
  await page.getByRole('button', { name: 'Save changes' }).first().click()
  await page.getByRole('button', { name: 'Approve plan' }).click()
  await page.getByText('Approved', { exact: true }).first().waitFor()
  await shot('p2-plan-approved')
  step('plan saved and approved')

  await page.getByText('Step finished').waitFor({ timeout: 90_000 }) // Chapter One started on approval
  await page.getByRole('tab', { name: /Chapter 1/ }).click()
  await page.getByRole('heading', { name: 'General Introduction' }).waitFor()
  await page.getByText('Readiness', { exact: true }).waitFor()
  await shot('p3-chapter-one')
  step('chapter one started by itself when the plan was approved, with its readiness checklist')

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

  // Supervisor feedback: pasted, placed on its section by PaperAid, applied by revising only that section.
  await page.getByRole('tab', { name: /Supervisor feedback/ }).click()
  await page.getByLabel("Paste your supervisor's comments").fill('1. In 1.2, give the size of the problem in Mukono.' + String.fromCharCode(10) + '2. Good work overall.')
  await page.getByRole('button', { name: 'Add these comments' }).click()
  await page.getByText('Comment 2').waitFor()
  if (!(await page.getByRole('checkbox', { name: '1.2 Statement of the Problem' }).isChecked())) throw new Error('comment 1 was not placed on 1.2')
  await page.getByRole('button', { name: 'I handled it myself' }).nth(1).click()
  await page.getByText('Done by you').waitFor()
  await shot('p5-feedback')
  step('supervisor comments pasted; one placed on 1.2 by PaperAid, the other marked done')
  await page.getByRole('tab', { name: /Chapter 1/ }).click()
  await runStep(page.getByRole('tabpanel').locator('div.rounded-xl', { hasText: "Revise from your supervisor's comments" }))
  await page.getByRole('tab', { name: /Supervisor feedback/ }).click()
  await page.getByText('Revised in version 2').waitFor({ timeout: 90_000 })
  step('chapter one revised from the comment; the comment records the version that answered it')
  await page.getByRole('tab', { name: /Chapter 1/ }).click()
  await page.getByRole('combobox', { name: 'Compare with' }).selectOption('1')
  await page.getByText('1 section changed.', { exact: false }).waitFor()
  await page.locator('ins', { hasText: 'supervisor' }).first().waitFor()
  await shot('p6-compare')
  step('versions compared: only the commented section changed')
  await page.getByRole('combobox', { name: 'Compare with' }).selectOption('0')
  await page.getByText('Figure 1.1: Conceptual framework').waitFor()
  step('the conceptual framework figure is drawn from the plan')
  await page.getByRole('tab', { name: /Ready/ }).click()
  await page.getByText('Write Chapter 2.', { exact: true }).waitFor()
  const [report] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Response to comments' }).click()])
  if (!report.suggestedFilename().startsWith('Response to supervisor')) throw new Error(`unexpected report: ${report.suggestedFilename()}`)
  await shot('p7-ready')
  step('the ready screen lists what is left; the response report downloads')

  await page.getByRole('tab', { name: 'Concept paper' }).click()
  await runStep(page.getByRole('tabpanel'))
  const conceptButton = page.getByRole('button', { name: 'Concept paper (Word)' })
  await conceptButton.waitFor({ timeout: 90_000 })
  await page.getByText('Is the concept paper at most five pages?').waitFor()
  const [concept] = await Promise.all([page.waitForEvent('download'), conceptButton.click()])
  if (!concept.suggestedFilename().endsWith('concept paper.docx')) throw new Error(`unexpected concept file: ${concept.suggestedFilename()}`)
  await shot('p8-concept')
  step('concept paper written from the plan, checked against its limits and downloaded')

  // Another institution: a new proposal follows the student's own research guide.
  await page.goto(`${base}/app/projects`)
  await page.getByRole('link', { name: 'New proposal' }).click()
  await page.getByLabel('Topic').fill('Teacher motivation and pupil performance in Kampala primary schools')
  await page.getByRole('button', { name: 'Create proposal' }).click()
  await page.waitForURL(/\/app\/projects\/prj_/)
  await page.getByRole('tab', { name: 'Details' }).click()
  await page.getByText('Written to the standard proposal structure', { exact: false }).waitFor()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'research-guide.docx', mimeType: 'application/octet-stream', buffer: readFileSync(new URL('./fixtures/research-guide.docx', import.meta.url)) })
  await runStep(page.getByRole('tabpanel').locator('div.rounded-xl', { hasText: "Use my institution's guide" }))
  await page.getByText('Kyambogo University', { exact: false }).first().waitFor({ timeout: 90_000 })
  await page.getByText('Check these with your supervisor').waitFor()
  await shot('p9-institution')
  step("a new proposal follows the student's institution, read from their guide")

  if (reviewFile) {
    await page.goto(`${base}/app/new?review=1`)
    await page.locator('input[type=file]').setInputFiles({ name: 'proposal.docx', mimeType: 'application/octet-stream', buffer: readFileSync(reviewFile) })
    await page.locator('aside dl').getByText('Proposal review', { exact: true }).waitFor({ timeout: 30_000 })
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
