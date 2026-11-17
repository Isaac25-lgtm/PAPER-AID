// What PaperAid adopted from PaperAid Pro (owner, 2026-11-17), in the browser against the local stack (web on :5000,
// tests.serve_e2e on :8000): each section's guide (a ghost-cursor walkthrough with captions and steps, collapsed and
// remembered), Help with every guide, the optional tour, the notifications bell, and night mode kept with the account.
// Run it after e2e-start.mjs, which leaves finished work on the demo account. Usage: node scripts/e2e-guides.mjs [dir]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'e2e-output'
const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath })
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } })
const problems = []
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('console', (m) => {
  if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) problems.push(`console: ${m.text()}`)
})
const step = (msg) => console.log(`✓ ${msg}`)
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

try {
  await page.goto(`${base}/sign-in`)
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('e2e-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/app/)
  await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('paperaid.guide.') || k === 'paperaid.tour').forEach((k) => localStorage.removeItem(k)))

  // The dashboard's guide: open the first time, its caption moves on, it collapses and stays collapsed.
  await page.goto(`${base}/app`)
  const guide = page.getByRole('region', { name: 'How Home works' })
  await guide.waitFor()
  const caption = guide.locator('[aria-live="polite"]')
  const first = await caption.innerText()
  await page.waitForFunction((text) => document.querySelector('section[aria-label="How Home works"] [aria-live="polite"]')?.textContent !== text, first, { timeout: 15_000 })
  await shot('guide-dashboard')
  await guide.getByRole('button', { name: 'Collapse' }).click()
  await page.getByRole('button', { name: 'How Home works' }).waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'How Home works' }).waitFor()
  if (await page.getByRole('region', { name: 'How Home works' }).count()) throw new Error('the collapsed guide opened again')
  step('the dashboard guide plays its walkthrough, collapses and stays collapsed')

  // Each section has its own guide.
  for (const [path, name] of [['/app/works?section=COURSEWORK', 'Coursework'], ['/app/projects?goal=CONCEPT', 'Research concept note'], ['/app/projects', 'Research proposal'],
    ['/app/works?section=CONCEPT_NOTE', 'Funding concept note'], ['/app/works?section=FUNDING_PROPOSAL', 'Funding proposal'],
    ['/app/new?service=PAPER_CHECK', 'Paper Check'], ['/app/new?service=ACADEMIC_FORMAT', 'Academic formatting']]) {
    await page.goto(`${base}${path}`)
    await page.getByRole('region', { name: `How ${name} works` }).waitFor()
  }
  await shot('guide-paper-check')
  step('every section opens its own guide')

  // Help holds every guide; the tour goes through them and is offered until finished or skipped.
  await page.goto(`${base}/app`)
  await page.getByRole('navigation', { name: 'App', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Help', exact: true }).first().click()
  const help = page.getByRole('dialog', { name: 'Help' })
  await help.waitFor()
  await help.getByRole('button', { name: 'Funding proposal' }).click()
  await help.getByText('A full proposal written to the call').waitFor()
  await shot('help-centre')
  await help.getByRole('button', { name: 'Take the tour of PaperAid' }).click()
  const tour = page.getByRole('dialog', { name: /1 of 8 · Home/ })
  await tour.waitFor()
  await page.getByRole('button', { name: 'Next' }).click()
  await page.getByRole('dialog', { name: /2 of 8 · Coursework/ }).waitFor()
  await page.getByRole('button', { name: 'Skip the tour' }).click()
  await page.reload()
  await page.getByText('Continue writing').first().waitFor()
  if (await page.getByRole('button', { name: 'New to PaperAid? Take the tour' }).count()) throw new Error('the tour is still offered after it was skipped')
  step('Help shows every guide; the tour steps through the sections and is not offered again once skipped')

  // The notifications bell: finished work is unread until the bell is opened.
  const bell = page.getByRole('button', { name: /Notifications/ }).first()
  await bell.waitFor()
  await page.waitForFunction(() => /unread/.test(document.querySelector('[aria-label^="Notifications"]')?.getAttribute('aria-label') ?? ''), null, { timeout: 10_000 })
    .catch(() => { throw new Error('the bell shows nothing unread after finished work') })
  await bell.click()
  await page.getByRole('menu').getByText(/is ready|stopped/).first().waitFor()
  await shot('notifications')
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !/unread/.test(document.querySelector('[aria-label^="Notifications"]')?.getAttribute('aria-label') ?? 'unread'), null, { timeout: 5_000 })
  step('the bell lists finished work as unread and clears it once opened')

  // Night mode is kept with the account: chosen here, it comes back in a browser that has never seen it.
  await page.getByRole('radio', { name: 'Night' }).click()
  await page.waitForTimeout(800)
  const fresh = await browser.newContext()
  const other = await fresh.newPage({ viewport: { width: 1440, height: 950 } })
  await other.goto(`${base}/sign-in`)
  await other.getByLabel('Email').fill('demo@paperaid.app')
  await other.getByLabel('Password').fill('e2e-password')
  await other.getByRole('button', { name: 'Sign in', exact: true }).click()
  await other.waitForURL(/\/app/)
  await other.waitForFunction(() => document.documentElement.dataset.theme === 'dark', null, { timeout: 10_000 })
  await fresh.close()
  await page.getByRole('radio', { name: 'Day' }).click()
  step('night mode chosen in one browser follows the account to another')

  if (problems.length) throw new Error(problems.join('\n'))
  console.log('\nguides journey passed')
} catch (e) {
  await shot('guides-failure').catch(() => {})
  console.error(e)
  process.exitCode = 1
} finally {
  await browser.close()
}
