// The works journeys against the local stack: web on :5000 and the browser-test backend on :8000
// (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles are test stand-ins.
// Coursework with a no-AI brief, a funding proposal with its Results Model and budget, and a
// research concept note that never starts Chapter One by itself.
// Usage: node scripts/e2e-works.mjs [screenshotDir]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
const problems = []
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('response', (r) => {
  if (r.status() >= 400) problems.push(`unexpected ${r.status()} from ${new URL(r.url()).pathname}`)
})
page.on('console', (m) => {
  if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) problems.push(`console: ${m.text()}`)
})
const step = (msg) => console.log(`✓ ${msg}`)
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
const aside = () => page.locator('aside')

async function run(label, notice) {
  await aside().getByText(label, { exact: true }).waitFor()
  await aside().getByRole('button', { name: 'See the price' }).click()
  if (notice) await aside().getByText(notice, { exact: false }).waitFor()
  await aside().getByRole('button', { name: 'Start' }).click()
  await aside().getByText('This takes a few minutes', { exact: false }).waitFor()
  await aside().getByText('This takes a few minutes', { exact: false }).waitFor({ state: 'detached', timeout: 120_000 })
}

async function understood(answers) {
  await page.getByRole('tab', { name: 'What PaperAid understood' }).click()
  for (const [label, value, kind] of answers) {
    const field = page.getByLabel(label, { exact: false }).first()
    if (kind === 'select') await field.selectOption({ label: value })
    else {
      await field.fill(value)
      await field.blur() // each answer saves as soon as the student leaves the box
    }
    await page.getByText('Saving…').first().waitFor({ state: 'detached' }).catch(() => {})
  }
  const confirm = page.getByRole('button', { name: 'This is right: confirm' })
  const defaults = page.getByRole('button', { name: "Use PaperAid's defaults for the rest" })
  // settled: either every question is answered (confirm enabled) or the remaining ones can take PaperAid's defaults
  const settled = async () => {
    for (let i = 0; i < 50; i++) {
      if (await confirm.isEnabled()) return
      if ((await defaults.count()) && (await defaults.isEnabled())) return
      await page.waitForTimeout(200)
    }
  }
  await settled()
  if (!(await confirm.isEnabled()) && (await defaults.count())) {
    await defaults.click()
    await settled()
  }
  await confirm.click()
  await page.getByText('You confirmed what PaperAid understood.').waitFor()
}


// New work starts with one Start (owner decision 2026-10-01); these journeys cover the earlier pages that
// work set up before it keeps, so they create that work directly through the API.
const DEV = { Authorization: 'Dev demo@paperaid.app' }
const INPUTS = { level: 'MASTERS', programme: '', faculty: '', studyArea: '', population: '', studyType: null, notes: '', populationSize: null, populationSource: '', expectedParticipants: null }
async function createWork(body) {
  const res = await page.request.post(`${base}/api/works`, { headers: DEV, data: body })
  if (!res.ok()) throw new Error(`creating a work: ${res.status()} ${await res.text()}`)
  const work = await res.json()
  await page.goto(`${base}/app/works/${work.id}`)
  await page.waitForURL(/\/app\/works\/wrk_/)
}
async function createProject(inputs, titlePage = {}, goal = 'FULL') {
  const res = await page.request.post(`${base}/api/projects`, {
    headers: DEV,
    data: { inputs: { ...INPUTS, ...inputs }, titlePage: { studentName: '', regNumber: '', supervisor: '', submissionDate: '', ...titlePage }, citation: 'APA6', goal },
  })
  if (!res.ok()) throw new Error(`creating a proposal: ${res.status()} ${await res.text()}`)
  const project = await res.json()
  await page.goto(`${base}/app/projects/${project.id}`)
  await page.waitForURL(/\/app\/projects\/prj_/)
}

try {
  await page.goto(`${base}/sign-in`)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app/)
  await page.goto(`${base}/admin/credits`) // payments aren't live: an admin adds test credits
  await page.getByLabel('Student email').fill('demo@paperaid.app')
  await page.getByLabel('Amount (credits)').fill('1000')
  await page.getByRole('button', { name: 'Add credits' }).click()
  await page.getByText(/Their balance is now/).first().waitFor()
  await page.goto(`${base}/app/new`)
  for (const section of ['Coursework', 'Funding']) await page.getByRole('heading', { name: section, exact: true }).waitFor()
  await page.getByText('AI detection').first().waitFor()
  await page.getByText('Coming soon').first().waitFor()
  step('the new sections are offered, and AI detection shows as coming soon')

  // --- coursework: an essay whose brief bans AI -----------------------------------------------
  await createWork({ kind: 'COURSEWORK', variant: 'ESSAY', mode: '', citation: 'APA7', inputs: { title: 'Community health workers and maternal health',
    description: 'Critically evaluate the effectiveness of community health workers in improving maternal health outcomes in rural Uganda since 2015.', answers: {}, experience: '' } })
  await understood([
    ['What word limit did your lecturer give you?', '1,500 words', 'fill'], // live case wrk_64b3b916e144: a limit typed with words
    ['What level is this work?', 'Later ug', 'select'],
    ['Does your assignment say anything about using AI?', 'Banned', 'select'],
  ])
  await page.getByText('at most 1,500 words', { exact: false }).first().waitFor() // the limit typed as "1,500 words" was saved and applied
  step('what PaperAid understood was answered (a limit typed with words, saved as it was given) and confirmed')
  await shot('w1-understood')
  await run('Make my plan')
  await aside().getByText('Review and approve your plan').waitFor()
  await aside().getByRole('button', { name: 'Open' }).click()
  await page.getByRole('button', { name: 'Approve the plan' }).click()
  await page.getByRole('button', { name: 'Approved' }).waitFor()
  step('the plan was drafted and approved')
  await run('Write my draft', 'AI-assisted third party')
  step('before buying, the student was told about the last-page note')
  await page.getByRole('tab', { name: 'Your draft' }).click()
  await page.getByText('Last page: This document was drafted by an AI-assisted third party.').waitFor()
  await page.getByText(/checks pass/).first().waitFor()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Word' }).click()])
  if (!download.suggestedFilename().endsWith('.docx')) throw new Error('no Word file')
  await shot('w2-coursework-document')
  step('the coursework draft shows its checks and last-page note, and downloads')

  // --- a funding proposal: Results Model, budget, tables ------------------------------------------
  await createWork({ kind: 'FUNDING_PROPOSAL', variant: 'NGO_PROJECT', mode: 'COMPACT', citation: 'APA7', inputs: { title: 'Safer deliveries in Kamuli',
    description: 'Too many mothers in Kamuli deliver at home without skilled care, and referrals are late.', answers: {}, experience: '' } })
  await understood([
    ['What do you propose to do about it?', 'Train village health teams and fund referral transport.', 'fill'],
    ['How many months will the work last?', '12', 'fill'],
  ])
  await run('Make my plan')
  await aside().getByRole('button', { name: 'Open' }).click()
  await page.getByRole('button', { name: 'Approve the plan' }).click()
  await page.getByRole('button', { name: 'Approved' }).waitFor()
  await page.getByRole('tab', { name: 'Results Model' }).click()
  await page.getByText('Baselines and targets are yours').waitFor()
  const targets = page.getByLabel('Target')
  for (let i = 0; i < (await targets.count()); i++) await targets.nth(i).fill(String(50 + i))
  await page.getByRole('button', { name: 'Approve the Results Model' }).click()
  await page.getByRole('button', { name: 'Approved' }).first().waitFor()
  step('the student completed and approved the Results Model (targets are theirs)')
  await page.getByRole('tab', { name: 'Budget' }).click()
  const quantities = page.getByLabel('Quantity')
  const costs = page.getByLabel('Unit cost')
  for (let i = 0; i < (await quantities.count()); i++) {
    await quantities.nth(i).fill('4')
    await costs.nth(i).fill('250')
  }
  await page.getByRole('button', { name: 'Save the budget' }).click()
  await page.getByText(/Total \(calculated by PaperAid when you save\): USD 3,000/).waitFor()
  step('budget totals come from the server')
  await run('Write my draft')
  await page.getByRole('tab', { name: 'Your draft' }).click()
  for (const caption of ['Logframe', 'Workplan', 'Budget summary']) await page.getByText(caption, { exact: true }).first().waitFor()
  await shot('w3-funding-document')
  step('the funding proposal has its logframe, workplan and budget tables, built from the data')

  // --- a research concept note: no Chapter One by itself -------------------------------------------
  await createProject({ topic: 'Malaria vaccine uptake among caregivers of young children in Mukono District' }, {}, 'CONCEPT')
  await page.getByRole('button', { name: 'See the price' }).click()
  if (await page.getByText('Plan and Chapter One together').count()) throw new Error('a concept note must not price Chapter One')
  await page.getByRole('button', { name: 'Start' }).click()
  await page.getByText('Step finished').waitFor({ timeout: 90_000 })
  await page.getByLabel('Accessible population (N)').fill('2400')
  await page.getByLabel('Where this figure comes from').fill('Mukono District Health Office records, 2025')
  await page.getByRole('button', { name: 'Save changes' }).first().click()
  // An edited plan is not what PaperAid reviewed: the student confirms their changes first (Codex audit 2026-10-01)
  const confirmEdits = page.getByLabel('I have checked these points and want to approve this plan')
  await confirmEdits.waitFor({ timeout: 15_000 }).catch(() => {}) // appears once the save has returned
  if (await confirmEdits.count()) await confirmEdits.check()
  await page.getByRole('button', { name: 'Approve plan' }).click()
  await page.getByText('Approved', { exact: true }).first().waitFor()
  await page.waitForTimeout(1500)
  if (await page.getByText('Queued').count()) throw new Error('approving a concept note plan started a step')
  if (await page.getByRole('tab', { name: 'Chapter 1' }).count()) throw new Error('a concept note shows no chapters')
  await page.getByRole('button', { name: 'Continue to the full proposal' }).click()
  await page.getByRole('tab', { name: 'Chapter 1' }).waitFor()
  step('a concept note never starts Chapter One, and continues into the full proposal')

  if (problems.length) throw new Error(problems.join('\n'))
  console.log('\nworks journey passed')
} catch (err) {
  await shot('w-failure').catch(() => {})
  console.error(err)
  if (problems.length) console.error(problems.join('\n'))
  process.exitCode = 1
} finally {
  await browser.close()
}
