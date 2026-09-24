// Visual review helper: captures every major route at phone and desktop widths, signed in as the
// local demo admin. Usage: node scripts/screenshots.mjs <outDir> [baseUrl]  (both servers running)
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const outDir = process.argv[2] ?? 'screenshots'
const base = process.argv[3] ?? 'http://localhost:5000'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const publicRoutes = ['/', '/features', '/pricing', '/privacy', '/sign-in', '/sign-up']
const demo = { Authorization: 'Dev demo@paperaid.app' }
const recent = await fetch(`${base}/api/jobs?limit=3`, { headers: demo }).then((r) => r.json())
const jobIds = recent.items.map((j) => j.id)
const appRoutes = ['/app', '/app/new', ...jobIds.map((id) => `/app/jobs/${id}`), '/app/history', '/app/settings', '/admin', ...jobIds.slice(0, 1).map((id) => `/admin/jobs/${id}`)]
const viewports = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } }
const demoUser = JSON.stringify({ email: 'demo@paperaid.app', displayName: 'Demo Student' })

mkdirSync(outDir, { recursive: true })
const browser = await chromium.launch({ executablePath })
const problems = []

for (const [name, viewport] of Object.entries(viewports)) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  const page = await context.newPage()
  page.on('console', (m) => m.type() === 'error' && problems.push(`${name} console: ${m.text()}`))
  page.on('pageerror', (e) => problems.push(`${name} pageerror: ${e.message}`))
  for (const route of [...publicRoutes, ...appRoutes]) {
    if (route === appRoutes[0]) await page.evaluate((u) => localStorage.setItem('paperaid.local-user', u), demoUser)
    await page.goto(base + route, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    if (overflow) problems.push(`${name} ${route}: horizontal overflow`)
    const file = `${outDir}/${name}${route.replaceAll('/', '_').replace(/job_\w+/, 'job') || '_home'}.png`
    await page.screenshot({ path: file, fullPage: true })
  }
  await context.close()
}

await browser.close()
console.log(problems.length ? problems.join('\n') : 'No console errors or horizontal overflow.')
