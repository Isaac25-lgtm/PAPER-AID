// Screenshots of the signed-in app for design review (redesign 2026-10-04), against the local stack:
// web on :5000 and the browser-test backend. Usage: node scripts/screens-app.mjs outDir [width]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const out = process.argv[2] ?? 'screens'
const width = Number(process.argv[3] ?? 1440)
const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const page = await browser.newPage({ viewport: { width, height: 900 } })
await page.goto(`${base}/sign-in`)
await page.getByLabel('Email').fill('demo@paperaid.app')
await page.getByLabel('Password').fill('e2e-password')
await page.getByRole('button', { name: 'Sign in', exact: true }).click()
await page.waitForURL(/\/app/)
const pages = [['home', '/app'], ['new', '/app/new'], ['work', '/app/work'], ['datalab', '/app/datalab'], ['works', '/app/works'], ['projects', '/app/projects'],
  ['paper-check', '/app/new?service=PAPER_CHECK'], ['start-coursework', '/app/start/coursework'], ['settings', '/app/settings']]
for (const [name, path] of pages) {
  await page.goto(`${base}${path}`)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true })
}
// the first piece of work of each kind, as the student sees it
await page.goto(`${base}/app/work`)
await page.waitForLoadState('networkidle').catch(() => {})
for (const [name, pattern] of [['work-doc', /\/app\/works\/wrk_/], ['proposal', /\/app\/projects\/prj_/], ['job', /\/app\/jobs\/job_/], ['dl-project', /\/app\/datalab\/dl_/]]) {
  const href = await page.evaluate((src) => [...document.querySelectorAll('a[href]')].map((a) => a.getAttribute('href')).find((h) => new RegExp(src).test(h)), pattern.source)
  if (!href) continue
  await page.goto(`${base}${href}`)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true })
}
await browser.close()
console.log('screens saved')
