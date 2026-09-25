// Critical-journey check against the local stack: web on :5000 and the browser-test backend on
// :8000 (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles are test stand-ins.
// Usage: node scripts/e2e.mjs [screenshotDir]
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = 'http://localhost:5000'
const fixtures = '../backend/tests/fixtures/generated/'
const jobsDir = '../backend/.data_e2e/jobs' // local store: one JSON file per job, drafts included
const jobCount = () => (existsSync(jobsDir) ? readdirSync(jobsDir).filter((f) => f.endsWith('.json')).length : 0)
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
const problems = []
// Every error response must be one the current step expects; anything else fails the run.
let expected = [] // [{ status, path: RegExp }]
const expect = (...rules) => (expected = rules)
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('response', (r) => {
  if (r.status() < 400) return
  const path = new URL(r.url()).pathname
  if (!expected.some((rule) => rule.status === r.status() && rule.path.test(path))) problems.push(`unexpected ${r.status()} from ${path}`)
})
page.on('console', (m) => {
  // "Failed to load resource" duplicates a response already judged above.
  if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) problems.push(`console: ${m.text()}`)
})
const step = (msg) => console.log(`✓ ${msg}`)
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })

async function upload(name, fileName = name) {
  await page.locator('input[type=file]').setInputFiles({ name: fileName, mimeType: 'application/octet-stream', buffer: readFileSync(fixtures + name) })
}

try {
  // Signed-out Upload goes to sign-in and comes back to the new-job page.
  await page.goto(base)
  await page.evaluate(() => localStorage.clear())
  await page.goto(base)
  await page.getByRole('link', { name: 'Upload your paper' }).first().click()
  await page.waitForURL(/sign-in\?next=%2Fapp%2Fnew/)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app\/new/)
  step('sign-in returns to the new-job page')

  // Payments aren't live: an admin adds test credits, as the owner will while testing.
  const chip = page.getByRole('link', { name: /^Credits: UGX / })
  await chip.waitFor()
  const startBalance = Number((await chip.getAttribute('aria-label')).replace(/[^0-9]/g, ''))
  await page.goto(`${base}/admin/credits`)
  await page.getByLabel('Student email').fill('demo@paperaid.app')
  await page.getByLabel('Amount (UGX)').fill('500000')
  await page.getByRole('button', { name: 'Add credits' }).click()
  const expected = (startBalance + 500000).toLocaleString('en')
  await page.getByText(`Their balance is now UGX ${expected}`).waitFor()
  await page.getByRole('link', { name: `Credits: UGX ${expected}` }).waitFor()
  step('admin added test credits; the header balance updated')
  await page.goto(`${base}/app/new`)

  // A bad file is rejected with the server's message.
  expect({ status: 422, path: /^\/api\/jobs\/job_\w+\/files\/source$/ })
  await upload('macro_renamed.docx', 'coursework.docx')
  await page.getByText('Macro-enabled Word files are not accepted').waitFor()
  expect()
  step('macro file rejected by the server')

  // Real upload → real inspection → real quote.
  await upload('dissertation_long.docx', 'Chapter drafts.docx')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.getByText('Academic formatting').first().click()
  await page.getByRole('combobox', { name: 'Formatting style' }).selectOption('harvard')
  await page.getByText('First, a short AI estimate').waitFor()
  await shot('1a-estimate-offer')
  await page.getByRole('button', { name: /Get my estimate/ }).click() // the paid scan only runs on the student's click
  await page.locator('aside dl').getByText('Academic formatting').waitFor({ timeout: 60000 })
  const quoteText = await page.locator('aside dl').innerText()
  await shot('1-quote')
  step(`quote: ${quoteText.replace(/\n/g, ' ')}`)
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  const jobUrl = page.url()
  step(`submitted ${jobUrl.split('/').pop()}`)

  // Live progress, then results.
  await page.getByRole('heading', { name: /working on your paper|in the queue/ }).waitFor()
  await shot('2-processing')
  await page.getByRole('tab', { name: 'Overview' }).waitFor({ timeout: 120000 })
  await shot('3-overview')
  step('job completed')
  for (const tab of ['Writing report', 'Changes', 'Formatting']) {
    await page.getByRole('tab', { name: tab }).click()
    await page.waitForTimeout(300)
    await shot(`4-${tab.toLowerCase().replace(' ', '-')}`)
  }
  step('result tabs render')

  // Real download of the refined + formatted Word file.
  await page.getByRole('tab', { name: 'Overview' }).click()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Download Refined and formatted paper/ }).click()])
  const path = `${out}/${download.suggestedFilename()}`
  await download.saveAs(path)
  const head = readFileSync(path).subarray(0, 2).toString()
  if (head !== 'PK') throw new Error('downloaded file is not a Word document')
  step(`downloaded "${download.suggestedFilename()}"`)

  // Regression (external review): a PDF uploaded the instant the page opens must quote on the
  // same draft it was uploaded to, and a visit must create exactly one draft.
  let before = jobCount()
  await page.goto(`${base}/app/new`)
  await page.waitForTimeout(600)
  if (jobCount() !== before) throw new Error('opening the new-job page created a draft before any upload')
  await upload('text_based.pdf', 'proposal.pdf')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.getByText('Needs a Word file').first().waitFor()
  await page.locator('aside dl').getByText('AI Check').waitFor()
  if (jobCount() !== before + 1) throw new Error(`expected 1 draft for this visit, found ${jobCount() - before}`)
  step('PDF uploaded immediately quotes on its own draft (one draft per visit)')

  // Replacing a Word file with a PDF in the same visit re-quotes on the same draft.
  before = jobCount()
  await page.goto(`${base}/app/new`)
  await upload('simple_essay.docx', 'essay.docx')
  await page.getByText('First, a short AI estimate').waitFor({ timeout: 20000 })
  await page.getByRole('button', { name: 'Remove essay.docx' }).click()
  await upload('text_based.pdf', 'essay.pdf')
  await page.locator('aside dl').getByText('AI Check').waitFor({ timeout: 20000 })
  if (await page.getByText('Upload your paper first').count()) throw new Error('quote landed on a different draft')
  if (jobCount() !== before + 1) throw new Error(`expected 1 draft after replacing the file, found ${jobCount() - before}`)
  step('replacing the file keeps one draft and re-quotes correctly')

  // University templates: the guide is required before pricing, then its rules are applied with sources.
  await page.goto(`${base}/app/new`)
  await upload('simple_essay.docx', 'Template essay.docx')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.locator('label', { hasText: 'University templates' }).click()
  await page.getByText('Upload your formatting guide to see the price').waitFor()
  await upload('guideline_university.docx', 'Old guide.docx')
  await page.getByText('First, a short AI estimate').waitFor({ timeout: 20000 })
  await page.getByRole('button', { name: 'Remove Old guide.docx' }).click() // removed on the server too
  await page.getByText('Upload your formatting guide to see the price').waitFor()
  await upload('guideline_university.docx', 'Department guide.docx')
  await page.getByRole('button', { name: /Get my estimate/ }).click()
  await page.locator('aside dl').getByText('University template formatting').waitFor({ timeout: 60000 })
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  await page.getByRole('tab', { name: 'Overview' }).waitFor({ timeout: 120000 })
  await page.getByRole('tab', { name: 'Formatting' }).click()
  await page.getByText('Where each rule came from in your guide').waitFor()
  await page.getByText('3.0 cm left').first().waitFor()
  await shot('7-template-formatting')
  await page.getByRole('tab', { name: 'Changes' }).click()
  await page.locator('details summary').first().click()
  await page.getByText('Why:').first().waitFor()
  step('university template job applies the guide with sources; changes say why')

  // Credits: every job settled, nothing left held, and the history explains each movement.
  await page.goto(`${base}/app/credits`)
  await page.getByText('Credits added').first().waitFor()
  await page.getByText(/Held · Held for your job/).first().waitFor()
  if (await page.getByText('held for work in progress').count()) throw new Error('credits still held after every job finished')
  await shot('8-credits')
  step('credits page shows the balance and the history of holds and settlements')

  // Dashboard and history show the job; admin console shows it with its stages.
  await page.goto(`${base}/app`)
  await page.getByText('Chapter drafts.docx').first().waitFor()
  await page.goto(`${base}/admin`)
  await page.getByText('demo@paperaid.app').first().waitFor()
  await shot('5-admin')
  await page.getByRole('link', { name: jobUrl.split('/').pop() }).click()
  await page.getByText('Timeline').waitFor()
  await shot('6-admin-job')
  step('admin console lists and details the job')

  // A second user cannot open the first user's job.
  expect({ status: 404, path: /^\/api\/jobs\/job_\w+$/ })
  await page.evaluate(() => localStorage.setItem('paperaid.local-user.v2', JSON.stringify({ email: 'someone.else@example.com', displayName: 'Else' })))
  await page.goto(jobUrl)
  await page.getByText("We couldn't find this job").waitFor()
  step("another user cannot see the job")
} catch (err) {
  problems.push(`FAILED: ${err.message}`)
  await shot('failure')
}

await browser.close()
console.log(problems.length ? `\nProblems:\n${problems.join('\n')}` : '\nAll checks passed with no page errors.')
process.exit(problems.length ? 1 : 0)
