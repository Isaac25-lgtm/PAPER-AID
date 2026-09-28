// Critical-journey check against the local stack: web on :5000 and the browser-test backend on
// :8000 (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles are test stand-ins.
// One screen from upload to final draft (owner request 2026-09-29): upload, the paper opens with the
// next step beside it, results on the same screen, then redraft, ask for changes or format.
// Usage: node scripts/e2e.mjs [screenshotDir]
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = 'http://localhost:5000'
const fixtures = '../backend/tests/fixtures/generated/'
const LOGO_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
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
const panel = () => page.locator('aside')

async function upload(name, fileName = name) {
  await page.locator('input[type=file]').first().setInputFiles({ name: fileName, mimeType: 'application/octet-stream', buffer: readFileSync(fixtures + name) })
}

/** Tick "own work", start, and wait on the same screen for the results. */
async function startAndFinish(button) {
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: button }).click()
  // The stand-in AI can finish before the page looks again, so the progress screen may never show.
  await page.getByRole('heading', { name: 'Your files' }).waitFor({ timeout: 240000 }) // every finished job shows its files
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
  await page.getByRole('heading', { name: 'What would you like PaperAid to do?' }).waitFor()
  await page.getByRole('link', { name: /Check \+ Refine/ }).click()
  await page.waitForURL(/\/app\/new\?service=REFINE/)
  await page.getByRole('heading', { name: 'Check + Refine' }).waitFor()
  await page.getByRole('link', { name: 'AI Check' }).first().click() // the top bar switches job from anywhere
  await page.waitForURL(/service=AI_CHECK/)
  await page.getByRole('heading', { name: 'AI Check' }).waitFor()
  step('new job starts by choosing the job; the top bar switches between services')

  // Payments aren't live: an admin adds test credits, as the owner will while testing.
  const chip = page.getByRole('link', { name: /^Tokens: / })
  await chip.waitFor()
  const startTokens = Number((await chip.getAttribute('aria-label')).replace(/[^0-9.]/g, ''))
  await page.goto(`${base}/admin/credits`)
  await page.getByLabel('Student email').fill('demo@paperaid.app')
  await page.getByLabel('Amount (tokens)').fill('500')
  await page.getByRole('button', { name: 'Add credits' }).click()
  const tokens = `${(startTokens + 500).toLocaleString('en', { maximumFractionDigits: 1 })} tokens`
  await page.getByText(`Their balance is now ${tokens}`).waitFor()
  await page.getByRole('link', { name: `Tokens: ${tokens}` }).waitFor()
  step('admin added test tokens; the header balance shows tokens')

  // --- AI Check: upload, the paper opens at once, check it, results on the same screen -------------
  await page.goto(`${base}/app/new?service=AI_CHECK`)
  expect({ status: 422, path: /^\/api\/jobs\/job_\w+\/files\/source$/ })
  await upload('macro_renamed.docx', 'coursework.docx')
  await page.getByText('Macro-enabled Word files are not accepted').waitFor()
  expect()
  step('a macro file is rejected with the server\'s message')
  await upload('simple_essay.docx', 'Checked essay.docx')
  await page.waitForURL(/\/app\/jobs\/job_\w+\?next=check/)
  await page.getByLabel('Your paper').getByText('Introduction', { exact: false }).first().waitFor({ timeout: 20000 })
  await panel().getByText('Check for AI', { exact: true }).first().waitFor()
  await panel().getByText('Academic, evidence and method review', { exact: true }).waitFor({ timeout: 20000 })
  await shot('1-uploaded-paper')
  step('the paper opens at once, with only "Check for AI" and its price beside it')
  await startAndFinish('Check for AI')
  await page.getByText('Estimated AI-likeness').first().waitFor()
  await page.getByText(/^\d{1,3}%$/).first().waitFor()
  await page.getByText(/AI patterns/).first().waitFor()
  await page.getByRole('button', { name: /^Next/ }).click()
  await page.locator('article').getByText(/Be specific|Replace|Vary|Say|Use/).first().waitFor()
  await shot('2-check-results')
  step('results on the same screen: a percentage, marked passages with labels, the report with Next')
  await page.getByRole('button', { name: /^Academic writing \(/ }).click()
  await page.getByRole('button', { name: 'Dismiss' }).first().click()
  await page.getByRole('button', { name: /Show 1 dismissed/ }).click()
  await page.getByRole('button', { name: 'Restore' }).first().click()
  await page.getByRole('button', { name: /^All \(/ }).click()
  step('findings by type: dismiss and restore')
  const checkedUrl = page.url().split('?')[0]
  await page.getByRole('checkbox').first().check()
  await page.getByRole('button', { name: 'Fix selected (1)' }).click()
  await page.waitForURL((u) => /\/app\/jobs\/job_\w+$/.test(u.toString()) && u.toString() !== checkedUrl)
  await panel().getByText('Your changes').waitFor()
  await panel().getByText('Check + Refine, standard').waitFor({ timeout: 30000 })
  step('fix selected opens the same paper with those passages and their price')
  await page.goto(checkedUrl)
  await page.getByRole('button', { name: 'Redraft my paper' }).click()
  await page.waitForURL(/next=redraft/)
  await panel().getByText('How much should change?').waitFor()
  step('Redraft opens the options only now, beside the same paper')

  // --- Redraft with options: style, formatting, logo, LaTeX; then keep or undo changes ---------------
  await page.goto(`${base}/app/new?service=REFINE`)
  await upload('dissertation_long.docx', 'Chapter drafts.docx')
  await page.waitForURL(/next=redraft/)
  await panel().getByRole('combobox', { name: 'Writing style' }).selectOption({ label: 'Concise academic' })
  await panel().getByText('Check my claims against live sources').click()
  await panel().getByText('APA, Harvard or another style').click()
  await panel().getByRole('combobox', { name: 'Style', exact: true }).selectOption('harvard')
  await panel().getByRole('button', { name: /Customise font/ }).click()
  await panel().getByRole('combobox', { name: 'Font', exact: true }).selectOption('Arial')
  await panel().getByText('Add an institution logo').click()
  await panel().getByText('Upload your logo to see the price').waitFor()
  await panel().locator('input[type=file]').last().setInputFiles({ name: 'crest.png', mimeType: 'image/png', buffer: Buffer.from(LOGO_PNG, 'base64') })
  await panel().getByText('crest.png').waitFor({ timeout: 20000 })
  await panel().getByRole('combobox', { name: 'Position' }).selectOption('LEFT')
  await panel().getByText('Also give me a LaTeX version').click()
  await panel().locator('dl').getByText('Academic formatting').waitFor({ timeout: 60000 })
  const quoteText = await panel().locator('dl').innerText()
  await shot('3-redraft-options')
  step(`redraft options with their price: ${quoteText.replace(/\n/g, ' ')}`)
  await page.reload() // a draft keeps its file and choices
  await panel().locator('dl').getByText('Academic formatting').waitFor({ timeout: 30000 })
  if ((await panel().locator('dl').innerText()) !== quoteText) throw new Error('the reloaded draft priced different choices')
  step('reloading keeps the paper, the choices and the price')
  const jobUrl = page.url().split('?')[0]
  await startAndFinish('Start redraft')
  await page.getByText('Your document is ready').waitFor()
  await page.getByText('Protected in your paper').waitFor()
  await page.getByText('Concise academic · standard refinement').waitFor()
  await shot('4-redrafted')
  step('the redrafted paper on the same screen, with what was protected')
  await page.getByRole('button', { name: 'Keep my wording' }).first().click()
  await page.getByText('Your wording', { exact: true }).first().waitFor()
  const [chosen] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download with my choices' }).click()])
  if (!chosen.suggestedFilename().includes('your choices')) throw new Error(`unexpected file: ${chosen.suggestedFilename()}`)
  step("a change undone; the Word file is rebuilt with the student's choices")
  for (const tab of ['Source check', 'Formatting', 'LaTeX']) {
    await page.getByRole('tab', { name: tab }).click()
    if (tab === 'Source check') await page.getByText('not that no evidence exists', { exact: false }).waitFor()
    if (tab === 'Formatting') {
      await page.getByText('Arial', { exact: false }).first().waitFor()
      await page.getByText('Logo', { exact: true }).first().waitFor()
    }
    if (tab === 'LaTeX') await page.getByText(/Compiled to PDF by PaperAid|Not compiled/).waitFor()
  }
  await page.getByRole('tab', { name: 'Your paper' }).click()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Download Refined and formatted paper/ }).click()])
  const path = `${out}/${download.suggestedFilename()}`
  await download.saveAs(path)
  if (readFileSync(path).subarray(0, 2).toString() !== 'PK') throw new Error('downloaded file is not a Word document')
  step(`downloaded "${download.suggestedFilename()}"; source check, formatting and LaTeX tabs render`)

  // --- Ask for changes on the finished draft, in the student's words -----------------------------
  await page.getByRole('button', { name: 'Ask for changes' }).click()
  await page.getByLabel('What should change?').fill('Make this paragraph shorter and more direct.')
  await page.locator('article p').nth(3).click()
  await page.getByText('Passages I pick (1)').waitFor()
  await shot('5-ask-for-changes')
  await page.getByRole('button', { name: 'See the price' }).click()
  await page.waitForURL((u) => /\/app\/jobs\/job_\w+$/.test(u.toString()) && !u.toString().startsWith(jobUrl))
  await panel().getByText('Make this paragraph shorter and more direct.', { exact: false }).waitFor()
  await startAndFinish('Make these changes')
  await page.getByText('Your document is ready').waitFor()
  step('ask for changes: the request becomes a priced revision of the finished paper, done on the same screen')
  await page.getByRole('button', { name: 'Format the finished paper' }).click()
  await page.waitForURL(/next=format/)
  await panel().locator('dl').getByText('Academic formatting').waitFor({ timeout: 30000 })
  step('format the finished paper opens with its layout options and price')

  // --- Deep redraft: a free preview first --------------------------------------------------------
  await page.goto(`${base}/app/new?service=REDRAFT`)
  await upload('citation_fields.docx', 'Chapter two.docx')
  await page.waitForURL(/next=redraft/)
  await panel().getByRole('button', { name: 'Preview my redraft' }).click()
  await panel().locator('dl').getByText('Deep redraft', { exact: true }).waitFor({ timeout: 60000 })
  await startAndFinish('Start redraft')
  await page.getByText('Passages redrafted').waitFor()
  step('deep redraft: a free preview, the price, then the redraft on the same screen')

  // --- A PDF can be checked; one visit makes one draft --------------------------------------------
  let before = jobCount()
  await page.goto(`${base}/app/new?service=AI_CHECK`)
  await page.waitForTimeout(600)
  if (jobCount() !== before) throw new Error('opening the upload page created a draft before any upload')
  await upload('text_based.pdf', 'proposal.pdf')
  await page.waitForURL(/next=check/)
  await panel().locator('dl').getByText('AI Check').waitFor({ timeout: 20000 })
  if (jobCount() !== before + 1) throw new Error(`expected 1 draft for this upload, found ${jobCount() - before}`)
  step('a PDF opens and is priced for a check (one draft per upload)')

  // --- University template: the guide first, then its rules with sources ---------------------------
  await page.goto(`${base}/app/new?service=TEMPLATE_FORMAT`)
  await upload('simple_essay.docx', 'Template essay.docx')
  await page.waitForURL(/next=format/)
  await panel().getByText('Upload your guide to see the price').waitFor()
  await panel().locator('input[type=file]').first().setInputFiles({ name: 'Department guide.docx', mimeType: 'application/octet-stream', buffer: readFileSync(fixtures + 'guideline_university.docx') })
  await panel().locator('dl').getByText('University template formatting').waitFor({ timeout: 60000 })
  await startAndFinish('Format my paper')
  await page.getByRole('tab', { name: 'Formatting' }).click()
  await page.getByText('Where each rule came from in your guide').waitFor()
  await page.getByText('3.0 cm left').first().waitFor()
  await shot('6-template-formatting')
  step('university template: the guide is read and its rules applied with sources')

  // Credits: every job settled, nothing left held, and the history explains each movement.
  await page.goto(`${base}/app/credits`)
  await page.getByText('Tokens added').first().waitFor()
  await page.getByText(/Held · Held for your job/).first().waitFor()
  if (await page.getByText('held for work in progress').count()) throw new Error('credits still held after every job finished')
  step('credits page shows the balance and the history of holds and settlements')

  // Dashboard and history show the job; admin console shows it with its stages.
  await page.goto(`${base}/app`)
  await page.getByText('Chapter drafts.docx').first().waitFor()
  await page.goto(`${base}/admin`)
  await page.getByText('demo@paperaid.app').first().waitFor()
  await page.getByRole('link', { name: jobUrl.split('/').pop() }).click()
  await page.getByText('Timeline').waitFor()
  step('admin console lists and details the job')

  // A second user cannot open the first user's job.
  expect({ status: 404, path: /^\/api\/jobs\/job_\w+$/ })
  await page.evaluate(() => localStorage.setItem('paperaid.local-user.v2', JSON.stringify({ email: 'someone.else@example.com', displayName: 'Else' })))
  await page.goto(jobUrl)
  await page.getByText("We couldn't find this job").waitFor()
  step('another user cannot see the job')
} catch (err) {
  problems.push(`FAILED: ${err.message}`)
  await shot('failure')
}

await browser.close()
console.log(problems.length ? `\nProblems:\n${problems.join('\n')}` : '\nAll checks passed with no page errors.')
process.exit(problems.length ? 1 : 0)
