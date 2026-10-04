// Data Lab (owner decision 2026-10-03) in the browser, against the local stack: web on :5000 and the
// browser-test backend on :8000 (cd backend && .venv/Scripts/python -m tests.serve_e2e), whose AI roles
// are test stand-ins. On one page: a dataset is uploaded and profiled, a change is confirmed and one
// declined, analyses and maps are run, the analysis report is written and downloaded, and the workbook
// is downloaded. Then a qualitative project: transcripts with names replaced, themes, report and codebook.
// Usage: node scripts/e2e-datalab.mjs [screenshotDir]
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const rows = ['id,name,sex,age,score,district,passed']
for (let i = 1; i <= 120; i++) {
  rows.push(`${String(i).padStart(4, '0')},Person ${i},${i % 2 ? 'Male ' : 'Female'},${20 + (i % 30)},${50 + ((i * 7) % 40)},${['Gulu', 'Pader', 'Kitgum'][i % 3]},${i % 3 ? 'yes' : 'no'}`)
}
rows.push('0121,Person 121,male,N/A,70,Gulu,yes')
const csv = join(out, 'exam-results.csv')
writeFileSync(csv, rows.join('\n') + '\n')

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
page.on('dialog', (d) => d.accept())
const problems = []
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('response', (r) => {
  if (r.status() >= 500) problems.push(`unexpected ${r.status()} from ${new URL(r.url()).pathname}`)
})
page.on('console', (m) => {
  if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) problems.push(`console: ${m.text()}`)
})
const step = (msg) => console.log(`✓ ${msg}`)
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
const LONG = { timeout: 120_000 }

try {
  await page.goto(`${base}/sign-in`)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app/)
  await page.goto(`${base}/admin/credits`) // payments aren't live: an admin adds test credits
  await page.getByLabel('Student email').fill('demo@paperaid.app')
  await page.getByLabel('Amount (credits)').fill('100')
  await page.getByRole('button', { name: 'Add credits' }).click()
  await page.getByText(/Their balance is now/).first().waitFor()

  await page.goto(`${base}/app/new`)
  await page.getByRole('heading', { name: 'Data analysis', exact: true }).waitFor()
  await page.getByRole('link', { name: /Map my data/ }).waitFor()
  await page.getByRole('link', { name: /Find the themes/ }).waitFor()
  await page.getByRole('link', { name: /Analyse my data/ }).click()
  await page.waitForURL(/\/app\/datalab\?new=QUANT$/)
  await page.getByLabel('Name of this analysis').fill('Exam results by sex')
  await page.getByLabel(/What do you want to find out/).fill('Do exam scores differ between female and male students?')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.waitForURL(/\/app\/datalab\/dl_/)
  step('Data Lab is offered on the New page and a project starts with its question')

  await page.getByLabel('Which country is this data from?').selectOption('KEN')
  await page.getByText(/isn't available yet for data from Kenya/).waitFor()
  await page.getByLabel('Which country is this data from?').selectOption('UGA')
  step('data from a country PaperAid is not cleared for is refused, with why')
  await page.locator('input[type=file]').first().setInputFiles(csv)
  await page.getByText(/removed on this device, before your file is sent/).waitFor()
  if (!(await page.getByRole('checkbox', { name: /"name" \(may identify people\)/ }).isChecked())) throw new Error('the name column was not ticked for removal')
  if (await page.getByRole('button', { name: 'Upload', exact: true }).isEnabled()) throw new Error('upload allowed before the confirmations')
  await page.getByRole('checkbox', { name: /I have the right to use this data/ }).check()
  await page.getByRole('checkbox', { name: /I have removed names, phone numbers/ }).check()
  await shot('dl1a-upload')
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await page.getByRole('button', { name: /Yes, make this change/ }).waitFor(LONG) // the data loads and opens on what needs confirming
  await shot('dl1-check')
  await page.getByText(/Removed on your device before upload: "name"/).waitFor()
  if (await page.getByLabel('Include name in analysis').count()) throw new Error('the removed column reached PaperAid')
  await shot('dl2-data')
  step('the name column is removed on the device before upload, after both confirmations')

  await page.getByRole('button', { name: /Yes, make this change/ }).click()
  await page.getByText(/you confirmed, version/).first().waitFor()
  while (await page.getByRole('button', { name: /No, keep it as it is/ }).count()) {
    await page.getByRole('button', { name: /No, keep it as it is/ }).click()
    await page.waitForTimeout(300)
  }
  await page.getByText('Nothing else needs your confirmation').waitFor()
  step('one change confirmed (a new version), the rest declined')

  await page.getByRole('button', { name: 'Choose an analysis' }).click()
  await page.getByRole('button', { name: /Describe one variable/ }).click()
  await page.getByLabel('Variable').selectOption({ label: 'district' })
  await page.getByRole('button', { name: 'Run the analysis' }).click()
  await page.getByRole('heading', { name: 'Summary of district' }).waitFor(LONG)
  await page.getByRole('button', { name: /Compare two groups/ }).click()
  await page.getByLabel('What to compare (a number)').selectOption({ label: 'score' })
  await page.getByLabel('The groups').selectOption({ label: 'sex' })
  await page.getByRole('button', { name: 'Run the analysis' }).click()
  await page.getByRole('heading', { name: 'score by sex' }).waitFor(LONG)
  await page.getByRole('button', { name: 'How this was calculated' }).first().click()
  await page.getByText('Why this method').first().waitFor()
  await shot('dl3-results')
  step('two analyses run by code, each with how it was calculated')

  await page.getByRole('button', { name: /Map of Uganda/ }).click()
  await page.getByLabel('The column with district names').selectOption({ label: 'district' })
  await page.getByRole('button', { name: 'Run the analysis' }).click()
  await page.getByRole('heading', { name: 'Records by district' }).waitFor(LONG)
  await page.getByAltText('Chart of this result').first().waitFor()
  await shot('dl3b-map')
  step('a district map of Uganda is drawn from the data')

  await page.getByRole('button', { name: /Map of Uganda/ }).click()
  await page.getByLabel('Map by').selectOption('SUBREGION')
  await page.getByLabel('The column with district names').selectOption({ label: 'district' })
  await page.getByRole('button', { name: 'Run the analysis' }).click()
  await page.getByRole('heading', { name: 'Records by sub-region' }).waitFor(LONG)
  step('a sub-region map (districts grouped as UBOS defines them)')

  await page.getByRole('button', { name: /Describe one variable/ }).click()
  await page.getByLabel('Variable').first().selectOption({ label: 'score' })
  await page.getByRole('button', { name: /Add a condition/ }).click()
  await page.getByLabel('Variable').nth(1).selectOption({ label: 'district' })
  await page.getByRole('checkbox', { name: 'Gulu' }).check()
  await page.getByRole('checkbox', { name: 'Pader' }).check()
  await page.getByRole('button', { name: 'Run the analysis' }).click()
  await page.getByRole('heading', { name: /Summary of score \(district is Gulu or Pader\)/ }).waitFor(LONG)
  await shot('dl3c-filter')
  step('an analysis limited to the records a filter keeps, named in its title')

  const workbook = page.waitForEvent('download')
  await page.getByRole('button', { name: /Report workbook/ }).first().click()
  if (!(await workbook).suggestedFilename().endsWith('.xlsx')) throw new Error('the workbook is not .xlsx')
  step('the report workbook (no individual records) downloads')

  const cleanedFile = page.waitForEvent('download', LONG)
  await page.getByRole('button', { name: /Cleaned data/ }).first().click()
  if (!(await cleanedFile).suggestedFilename().endsWith('cleaned data.xlsx')) throw new Error('the cleaned data is not its own .xlsx')
  step('the cleaned data is made by the worker and downloads as its own file')

  await page.getByRole('button', { name: /Write the report/ }).click()
  await page.getByRole('button', { name: /Write my analysis report/ }).click()
  await page.getByRole('button', { name: /Download Word/ }).waitFor(LONG)
  await page.getByRole('heading', { name: /Executive summary/ }).waitFor()
  await page.getByRole('heading', { name: /Appendix C. Data dictionary/ }).waitFor()
  await shot('dl4-report')
  const word = page.waitForEvent('download')
  await page.getByRole('button', { name: /Download Word/ }).click()
  if (!(await word).suggestedFilename().endsWith('.docx')) throw new Error('the report is not .docx')
  step('the analysis report is written, shown and downloads as Word')

  await page.goto(`${base}/app/work`)
  await page.getByText('Exam results by sex').first().waitFor()
  step('Your work lists the Data Lab project')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(page.url().replace('/app/work', '/app/datalab'))
  await page.getByText('Exam results by sex').first().click()
  await page.getByRole('button', { name: /Download Word/ }).waitFor()
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  await shot('dl5-phone')
  if (wide) throw new Error('the page scrolls sideways at phone width')
  step('phone width')

  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`${base}/app/datalab?new=QUAL`)
  await page.getByLabel('Name of this analysis').fill('Reaching care in Kamuli')
  await page.getByLabel(/Your research question/).fill('How do mothers reach a health facility to give birth?')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.waitForURL(/\/app\/datalab\/dl_/)
  const transcripts = [
    ['Interview 1', 'Agnes Akello lives far from the health centre. The walk to the clinic takes most of the morning for women in our village. When labour starts at night there is no transport, so many mothers stay at home.'],
    ['Interview 2', 'The boda boda riders charge a lot when it rains and the road floods. Mothers wait for the river to go down before they travel. Agnes said the health workers are kind but the distance is the problem for everyone here.'],
  ]
  for (const [label, text] of transcripts) {
    await page.getByRole('tab', { name: 'Paste text' }).click()
    await page.getByLabel('Name in the report').fill(label)
    await page.getByLabel('Transcript', { exact: true }).fill(text)
    await page.getByLabel(/Names to replace/).fill(['Agnes Akello = Participant A', 'Agnes = Participant A'].join('\n'))
    await page.getByRole('checkbox', { name: /My participants agreed/ }).check()
    await page.getByRole('button', { name: 'Add transcript' }).click()
    await page.getByText(new RegExp(`${label} · `)).waitFor()
  }
  await page.getByText(/2 transcripts/).first().waitFor()
  await shot('dl6-qual')
  step('a qualitative project on one page: two transcripts added with names replaced')

  await page.getByRole('button', { name: /Find the themes/ }).click()
  await page.getByRole('button', { name: /Codebook/ }).waitFor(LONG)
  await page.getByRole('heading', { name: /^\d+\. Themes$/ }).waitFor()
  await page.getByRole('heading', { name: /Appendix A. Codebook/ }).waitFor()
  const shown = (await page.evaluate(() => document.body.innerText)).replace(/e\.g\. Agnes Akello = Participant A/g, '')
  if (shown.includes('Agnes')) throw new Error('a replaced name reached the report')
  const codebook = page.waitForEvent('download')
  await page.getByRole('button', { name: /Codebook/ }).click()
  if (!(await codebook).suggestedFilename().endsWith('codebook.xlsx')) throw new Error('the codebook is not .xlsx')
  await shot('dl7-themes')
  step('themes found, the report shown, and the codebook downloads')

  if (problems.length) throw new Error(problems.join('\n'))
  console.log('\nData Lab journey passed.')
} catch (err) {
  await shot('dl-failure').catch(() => {})
  console.error('FAILED:', err.message)
  if (problems.length) console.error(problems.join('\n'))
  process.exitCode = 1
} finally {
  await browser.close()
}
