// Critical-journey check against the local stack: web on :5000 and the browser-test backend on
// :8000 (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles are test stand-ins.
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
  const expected = `${(startTokens + 500).toLocaleString('en', { maximumFractionDigits: 1 })} tokens`
  await page.getByText(`Their balance is now ${expected}`).waitFor()
  await page.getByRole('link', { name: `Tokens: ${expected}` }).waitFor()
  step('admin added test tokens; the header balance shows tokens')
  await page.goto(`${base}/app/new?service=REFINE`)

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
  // The student's own settings over the style, and an institution logo on the first page.
  await page.getByRole('button', { name: /Customise font/ }).click()
  await page.getByRole('combobox', { name: 'Font', exact: true }).selectOption('Arial')
  await page.getByText('Add an institution logo').click()
  await page.getByText('Upload your logo to see the price', { exact: false }).or(page.getByText('Choose your logo')).first().waitFor()
  await page.locator('input[type=file]').last().setInputFiles({ name: 'crest.png', mimeType: 'image/png', buffer: Buffer.from(LOGO_PNG, 'base64') })
  await page.getByText('crest.png').waitFor({ timeout: 20000 })
  await page.getByRole('combobox', { name: 'Position' }).selectOption('LEFT')
  step('own font chosen and a logo uploaded for the first page')
  await page.getByText('Concise academic').click() // the writing style is part of what is priced
  await page.getByText('Check my claims against live sources').click()
  await page.getByText('Also convert to LaTeX').click()
  // Fixed prices: refinement is priced at once, no estimate step.
  await page.locator('aside dl').getByText('Academic formatting').waitFor({ timeout: 60000 })
  await page.getByText('This is the price.', { exact: false }).waitFor()
  const quoteText = await page.locator('aside dl').innerText()
  await shot('1-quote')
  step(`fixed-price quote: ${quoteText.replace(/\n/g, ' ')}`)
  // A refresh keeps the draft: the file, the chosen services and the quote come back from the server.
  if (!/[?&]draft=job_/.test(page.url())) throw new Error(`the draft is not in the address: ${page.url()}`)
  await page.reload()
  await page.getByText('Chapter drafts.docx').first().waitFor({ timeout: 20000 })
  await page.locator('aside dl').getByText('Academic formatting').waitFor({ timeout: 20000 })
  const resumedQuote = await page.locator('aside dl').innerText()
  if (resumedQuote !== quoteText) throw new Error(`the resumed quote differs: ${resumedQuote}`)
  step('refreshing resumes the draft with the same quote')
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  const jobUrl = page.url()
  step(`submitted ${jobUrl.split('/').pop()}`)

  // Live progress, then results.
  await page.getByRole('heading', { name: /working on your paper|in the queue/ }).waitFor()
  await shot('2-processing')
  await page.getByRole('tab', { name: 'Your paper' }).waitFor({ timeout: 120000 })
  await page.getByText('Your document is ready').waitFor()
  await page.getByText('Protected in your paper').waitFor()
  await shot('3-workspace')
  step('job completed: the workspace shows the paper, the outcome and what was protected')
  await page.getByText('Concise academic · standard refinement').waitFor()
  // Keep one passage in the student's own words, then download a file with those choices.
  await page.getByRole('button', { name: 'Keep my wording' }).first().click()
  await page.getByText('Your wording', { exact: true }).first().waitFor()
  const [chosen] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download with my choices' }).click()])
  if (!chosen.suggestedFilename().includes('your choices')) throw new Error(`unexpected file: ${chosen.suggestedFilename()}`)
  step('a change undone in the workspace; the Word file is rebuilt with the student\'s choices')
  await page.getByRole('tab', { name: /Findings/ }).click()
  await page.getByRole('button', { name: /^All \(/ }).waitFor()
  for (const tab of ['Source check', 'Formatting', 'LaTeX']) {
    await page.getByRole('tab', { name: tab }).click()
    await page.waitForTimeout(300)
    await shot(`4-${tab.toLowerCase().replace(' ', '-')}`)
    if (tab === 'Source check') await page.getByText('not that no evidence exists', { exact: false }).waitFor()
    if (tab === 'Formatting') {
      await page.getByText('Arial', { exact: false }).first().waitFor()
      await page.getByText('Logo', { exact: true }).first().waitFor()
    }
    if (tab === 'LaTeX') await page.getByText(/Compiled to PDF by PaperAid|Not compiled/).waitFor()
  }
  step('result tabs render, with the chosen style and the findings')

  // Real download of the refined + formatted Word file.
  await page.getByRole('tab', { name: 'Your paper' }).click()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Download Refined and formatted paper/ }).click()])
  const path = `${out}/${download.suggestedFilename()}`
  await download.saveAs(path)
  const head = readFileSync(path).subarray(0, 2).toString()
  if (head !== 'PK') throw new Error('downloaded file is not a Word document')
  step(`downloaded "${download.suggestedFilename()}"`)
  const [zip] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Download LaTeX project/ }).click()])
  if (!zip.suggestedFilename().endsWith('.zip')) throw new Error(`LaTeX download is not a zip: ${zip.suggestedFilename()}`)
  step(`downloaded "${zip.suggestedFilename()}"`)

  // Deep Redraft: a separate job the student chooses, with the style picker and a full change report.
  await page.goto(`${base}/app/new?service=REFINE`)
  await upload('citation_fields.docx', 'Chapter two.docx')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.getByText('Deep redraft', { exact: true }).first().click()
  await page.getByText('What Deep Redraft changes').waitFor()
  await page.getByText('First, a free preview').waitFor()
  await page.getByRole('button', { name: 'Preview my redraft' }).click()
  await page.locator('aside dl').getByText('Deep redraft', { exact: true }).waitFor({ timeout: 60000 })
  await page.getByText(/Estimated change: about \d+% of your paper/).waitFor()
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  await page.getByRole('tab', { name: 'Your paper' }).waitFor({ timeout: 120000 })
  await page.getByText('Passages redrafted').waitFor()
  await page.getByText('Preserve my voice · deep redraft').waitFor()
  step('Deep Redraft job: estimate, quote, redraft and change report')

  // AI Check workspace: findings by type, dismiss and restore, then fix the chosen ones.
  await page.goto(`${base}/app/new?service=AI_CHECK`)
  await upload('simple_essay.docx', 'Checked essay.docx')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.getByText('Is this academic or research work?').waitFor()
  await page.locator('aside dl').getByText('Academic, evidence and method review', { exact: true }).waitFor({ timeout: 20000 })
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  await page.getByRole('tab', { name: 'Your paper' }).waitFor({ timeout: 120000 })
  await page.getByRole('button', { name: /^Academic writing \(/ }).click()
  await page.getByRole('button', { name: 'Dismiss' }).first().click()
  await page.getByRole('button', { name: /Show 1 dismissed/ }).click()
  await page.getByRole('button', { name: 'Restore' }).first().click()
  await page.getByRole('button', { name: /^All \(/ }).click()
  await page.getByRole('checkbox').first().check()
  await shot('5-ai-check-workspace')
  await page.getByRole('button', { name: 'Fix selected (1)' }).click()
  await page.waitForURL(/\/app\/new\?draft=job_\w+&service=REFINE/)
  await page.getByText(/Fixing 1 passage you chose/).waitFor()
  await page.locator('aside dl').getByText('Check + Refine, standard').waitFor({ timeout: 30000 })
  step('AI Check workspace: findings by type, dismiss and restore, fix selected opens a priced refinement')

  // Regression (external review): a PDF uploaded the instant the page opens must quote on the
  // same draft it was uploaded to, and a visit must create exactly one draft.
  let before = jobCount()
  await page.goto(`${base}/app/new?service=REFINE`)
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
  await page.goto(`${base}/app/new?service=REFINE`)
  await upload('simple_essay.docx', 'essay.docx')
  await page.locator('aside dl').getByText('Check + Refine, standard').waitFor({ timeout: 20000 })
  await page.getByRole('button', { name: 'Remove essay.docx' }).click()
  await upload('text_based.pdf', 'essay.pdf')
  await page.locator('aside dl').getByText('AI Check').waitFor({ timeout: 20000 })
  if (await page.getByText('Upload your paper first').count()) throw new Error('quote landed on a different draft')
  if (jobCount() !== before + 1) throw new Error(`expected 1 draft after replacing the file, found ${jobCount() - before}`)
  step('replacing the file keeps one draft and re-quotes correctly')

  // University templates: the guide is required before pricing, then its rules are applied with sources.
  await page.goto(`${base}/app/new?service=REFINE`)
  await upload('simple_essay.docx', 'Template essay.docx')
  await page.getByText('Readable text found').waitFor({ timeout: 20000 })
  await page.locator('label', { hasText: 'University templates' }).click()
  await page.getByText('Upload your formatting guide to see the price').waitFor()
  await upload('guideline_university.docx', 'Old guide.docx')
  await page.locator('aside dl').getByText('University template formatting').waitFor({ timeout: 20000 })
  await page.getByRole('button', { name: 'Remove Old guide.docx' }).click() // removed on the server too
  await page.getByText('Upload your formatting guide to see the price').waitFor()
  await upload('guideline_university.docx', 'Department guide.docx')
  await page.locator('aside dl').getByText('University template formatting').waitFor({ timeout: 60000 })
  await page.getByLabel(/This is my own work/).check()
  await page.getByRole('button', { name: /Start job/ }).click()
  await page.waitForURL(/\/app\/jobs\/job_/)
  await page.getByRole('tab', { name: 'Your paper' }).waitFor({ timeout: 120000 })
  await page.getByText('Why:').first().waitFor()
  await page.getByRole('tab', { name: 'Formatting' }).click()
  await page.getByText('Where each rule came from in your guide').waitFor()
  await page.getByText('3.0 cm left').first().waitFor()
  await shot('7-template-formatting')
  step('university template job applies the guide with sources; changes say why')

  // Credits: every job settled, nothing left held, and the history explains each movement.
  await page.goto(`${base}/app/credits`)
  await page.getByText('Tokens added').first().waitFor()
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
