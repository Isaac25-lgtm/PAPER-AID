// One Start (owner decision 2026-10-01) in the browser, against the local stack: web on :5000 and the
// browser-test backend on :8000 (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles
// are test stand-ins. Coursework, a funding proposal drafted with its missing figures then filled in,
// and a research proposal's Chapter One with its framework figure: each from the New page to the
// workspace, with no plan, approval or price screen on the way.
// Usage: node scripts/e2e-start.mjs [screenshotDir]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
page.on('dialog', (d) => d.accept()) // "Download anyway?" and stop confirmations
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
const LONG = { timeout: 240_000 }
const DEV = { Authorization: 'Dev demo@paperaid.app' } // the browser-test backend's sign-in, for reading what was saved

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

  // The dashboard and the New page: work first, every service under New.
  await page.goto(`${base}/app`)
  await page.getByRole('heading', { name: 'Start something new' }).waitFor()
  await page.getByText(/credits/).first().waitFor()
  await shot('01-dashboard')
  await page.goto(`${base}/app/new`)
  for (const group of ['Coursework', 'Research proposals', 'Funding']) await page.getByRole('heading', { name: group, exact: true }).waitFor()
  await shot('02-new')
  step('dashboard and New page')

  // --- coursework ---------------------------------------------------------------------------------------
  await page.getByRole('link', { name: /Start coursework/ }).click()
  await page.getByRole('heading', { name: 'What is your coursework?' }).waitFor()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByText('Paste your question to continue.').waitFor() // the error says what is needed, beside the field
  await page.getByLabel(/Your question or title/).fill('Critically evaluate the effectiveness of community health workers in improving maternal health outcomes in rural Uganda since 2015.')
  await shot('03-coursework-page1')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: 'A few details' }).waitFor()
  await page.getByLabel(/^Word limit/).first().selectOption('1500')
  for (const label of [/level is this work/i, /referencing style/i, /using AI/i]) {
    const field = page.getByLabel(label).first()
    if ((await field.count()) && (await field.evaluate((e) => e.tagName)) === 'SELECT') await field.selectOption({ index: 1 })
  }
  await shot('04-coursework-page2')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.waitForURL(/\/app\/works\//)
  await page.getByText('Writing your coursework').waitFor()
  await shot('05-coursework-progress')
  await page.getByRole('button', { name: /Download Word/ }).waitFor(LONG)
  await page.getByText('Ask for changes').first().waitFor()
  await shot('06-coursework-workspace')
  const word = page.waitForEvent('download')
  await page.getByRole('button', { name: /Download Word/ }).click()
  if (!(await word).suggestedFilename().endsWith('.docx')) throw new Error('the Word download is not a .docx')
  step('coursework: one Start to the workspace, Word downloads')

  await page.getByLabel(/Tell us what to change/).fill('Add a sentence on supervision of community health workers in the discussion.')
  await page.getByRole('button', { name: /Apply changes/ }).click()
  await page.getByText(/Applying your changes/).waitFor()
  await page.getByText(/Applying your changes/).waitFor({ state: 'detached', ...LONG })
  await page.getByRole('button', { name: /^Versions/ }).click()
  await page.getByText('Version 2').waitFor()
  await shot('07-coursework-changed')
  step('coursework: ask for changes makes version 2')

  // --- a funding proposal: drafted with its missing figures marked, then filled in ---------------------------
  await page.goto(`${base}/app/start/funding`)
  await page.getByRole('heading', { name: 'Your funding proposal' }).waitFor()
  await page.getByLabel(/Project title/).fill('Safer deliveries in Kamuli')
  await page.getByLabel(/The problem, and who it affects/).fill('Too many mothers in Kamuli deliver at home and die of preventable complications that a timely referral would prevent.')
  await page.getByLabel(/What you propose to do about it/).fill('We will train village health teams to spot danger signs and fund referral transport to the nearest health centre.')
  await page.getByLabel(/Or paste the call/).fill('The Maternal Health Fund invites proposals from registered NGOs in Uganda for projects that reduce maternal deaths through community referral. Projects run for twelve months.')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: 'A few details' }).waitFor(LONG)
  // Page 1 of a saved work (a reload, or back to change the documents) is that same work, never a second one.
  const fundingId = new URL(page.url()).searchParams.get('work')
  await page.goto(`${base}/app/start/funding?draft=${fundingId}`)
  await page.getByText('Your pasted call is saved. Paste the text again to replace it.').waitFor()
  if ((await page.getByLabel(/Project title/).inputValue()) !== 'Safer deliveries in Kamuli') throw new Error('page 1 lost the saved title')
  await page.getByLabel(/Or paste the call/).fill('The Maternal Health Fund invites proposals from registered NGOs in Uganda for projects that reduce maternal deaths through community referral and emergency transport. Projects run for twelve months.')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: 'A few details' }).waitFor(LONG)
  if (new URL(page.url()).searchParams.get('work') !== fundingId) throw new Error('page 1 made a second work')
  const calls = (await (await page.request.get(`${base}/api/works/${fundingId}`, { headers: DEV })).json()).sources.filter((s) => s.role === 'CALL')
  if (calls.length !== 1) throw new Error(`a replaced pasted call left ${calls.length} calls`)
  step('funding: page 1 reopened continues the same work, and a pasted call is replaced, not added')
  for (const [label, value] of [[/Your organisation: what it is/i, 'Kamuli Women Health Network, a registered NGO running maternal health projects since 2018'], [/Where will the work take place/i, 'Kamuli District, Uganda'], [/How much will you request/i, '50000'], [/How many months/i, '12']]) {
    const field = page.getByLabel(label).first()
    if ((await field.count()) && (await field.evaluate((e) => e.tagName)) !== 'SELECT') await field.fill(value)
  }
  const currency = page.getByLabel(/currency/i).first()
  if (await currency.count()) await currency.selectOption({ index: 1 })
  const confirm = page.getByLabel(/These are right/)
  if (await confirm.count()) await confirm.check()
  for (const eligibility of await page.getByLabel(/Do you meet this eligibility criterion/).all()) await eligibility.selectOption('yes')
  await shot('08-funding-page2')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.waitForURL(/\/app\/works\//)
  await page.getByRole('button', { name: /Download Word/ }).waitFor(LONG)
  await page.getByText(/Needs your input/).first().waitFor()
  await page.getByText('[to be added]').first().waitFor()
  await shot('09-funding-needs-input')
  for (const box of await page.locator('aside').getByLabel(/^(Baseline|Target)/).all()) await box.fill('40')
  for (const box of await page.locator('aside').getByLabel(/^(Quantity|Unit cost)/).all()) await box.fill('5')
  await page.getByRole('button', { name: 'Save figures' }).click()
  await page.getByText('[to be added]').first().waitFor({ state: 'detached', timeout: 60_000 })
  await shot('10-funding-filled')
  step('funding: drafted with marked gaps, figures filled in without AI')

  // --- a research proposal: one Start to Chapter One with its framework figure ---------------------------------
  await page.goto(`${base}/app/start/proposal`)
  await page.getByLabel(/Working title or topic/).fill('Factors associated with malaria vaccine uptake among children aged 6–24 months in Lira District')
  await page.getByText('PaperAid writes to the standard research structure.').waitFor() // owner decision 2026-10-08: one short line
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('heading', { name: 'About your study' }).waitFor()
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.getByText('Your name goes on the title page.').waitFor() // only the name is required
  if (await page.getByText(/Use the standard sample-size settings/).count()) throw new Error('the sample-size tick is back on the Start page')
  await page.getByLabel(/Your name/).fill('Grace Namukasa') // where, who, registration number and faculty left blank
  await shot('11-proposal-page2')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.waitForURL(/\/app\/projects\//)
  await page.getByRole('button', { name: /Download Word/ }).waitFor(LONG)
  await page.getByRole('tab', { name: /Chapter One/ }).waitFor()
  await page.getByRole('img', { name: /The study will examine the association/ }).waitFor()
  await page.getByRole('link', { name: 'Download the figure' }).waitFor()
  await page.getByText('Confirm your study setting').waitFor() // what PaperAid proposed stays marked as proposed
  await page.getByText("Align with my institution's guidelines").waitFor()
  await page.getByText('Conceptual framework', { exact: true }).waitFor()
  await shot('12-proposal-workspace')
  await page.getByRole('button', { name: 'These are right' }).click()
  await page.getByText('Confirm your study setting').waitFor({ state: 'detached' })
  step('proposal: one Start (name only) to Chapter One with its framework figure; the proposed setting confirmed')

  await page.getByRole('button', { name: /Continue to Chapter Two/ }).click()
  await page.getByRole('tab', { name: /Chapter Two/, selected: true }).waitFor() // the chapter being written opens, as Chapter One did
  await page.getByRole('tab', { name: /Chapter Two.*written/ }).waitFor(LONG)
  await shot('12b-chapter-two')
  if (await page.getByText(/Applying your changes/).count()) throw new Error('a chapter being written was shown as applying changes')
  step('proposal: Continue to Chapter Two opens it, with its progress, until it is written')

  // Your work lists all three.
  await page.goto(`${base}/app/work`)
  await page.getByText('Safer deliveries in Kamuli').first().waitFor()
  await shot('13-your-work')
  step('your work lists everything')

  // A phone: the workspace stacks, nothing scrolls sideways.
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${base}/app/new`)
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  if (wide) throw new Error('the New page scrolls sideways on a phone')
  await shot('14-phone-new')
  step('phone width')

  const unexpected = problems.filter((p) => !/unexpected 40[29] from \/api\/works\/[^/]+\/start/.test(p))
  if (unexpected.length) throw new Error(unexpected.join('\n'))
  console.log('All one-Start journeys passed.')
} catch (e) {
  await shot('failure').catch(() => {})
  console.error(e)
  console.error(problems.join('\n'))
  process.exitCode = 1
} finally {
  await browser.close()
}
