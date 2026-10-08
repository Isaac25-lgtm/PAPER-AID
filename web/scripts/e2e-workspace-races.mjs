// Synthetic response-order regressions. Run against the LOCAL browser-test stack; no jobs or model calls.
// node scripts/e2e-workspace-races.mjs
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const base = 'http://localhost:5000'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext()
context.setDefaultTimeout(30_000)
await context.addInitScript(() => localStorage.setItem('paperaid.local-user.v2', JSON.stringify({ email: 'demo@paperaid.app', displayName: 'Audit' })))
const stamp = (version) => `2026-10-08T10:00:0${version}.000000Z`
const versions = [1, 2].map((version) => ({ version, createdAt: stamp(version), words: 100, note: '', jobId: `job_race${version}`, planVersion: 1, passed: 0, total: 0 }))
const body = (name, version) => `${name} VERSION ${version} CURRENT TEXT`

function work(id, version, running) {
  return { id, kind: 'COURSEWORK', variant: 'ESSAY', level: 'MASTERS', citation: 'APA7', inputs: { title: id }, plan: null,
    documents: versions, current: version, activeJob: running ? 'job_synthetic' : null, auto: true, autoFailure: '',
    updatedAt: stamp(version), results: null, budget: null, requests: [], readiness: [] }
}
function project(id, version, running) {
  return { id, inputs: { topic: id, level: 'MASTERS' }, titlePage: {}, goal: 'FULL', plan: null, planStatus: 'APPROVED',
    planVersion: 1, auto: true, autoFailure: '', activeJob: running ? 'job_synthetic' : null, framework: '',
    rulebook: 'ucu-2018-v2', institution: 'Standard guide', institutionNotes: [], guideQuestions: [], guideName: null, guideRead: false, profileMissing: false,
    planProblems: [], blockers: [], proposed: [], written: [], acknowledgments: [],
    updatedAt: stamp(version), feedback: [], chapters: [1, 2, 3, 4].map((number) => ({ number,
      current: number === 1 ? version : 0, approved: false, needsReview: [], versions: number === 1 ? versions : [] })) }
}
function document(name, version) {
  return { version, title: name, status: 'READY', exploratory: false, sections: [{ key: 'body', heading: 'Discussion',
    paragraphs: [body(name, version)], table: null, tableCaption: '', fieldLimit: '', fieldCount: '' }],
    references: [], readiness: [], words: 100, aiNote: '', tables: [], revised: [] }
}
function chapter(name, version) {
  return { ...document(name, version), number: 1, planVersion: 1, warnings: [], missing: [], framework: [] }
}
function deferred() {
  let resolve
  const promise = new Promise((yes, no) => {
    const timer = setTimeout(() => no(new Error('Expected race-test request did not arrive')), 30_000)
    resolve = (value) => { clearTimeout(timer); yes(value) }
  })
  return { promise, resolve }
}
async function navigate(page, path) {
  // A client-side route change, preserving the JS application and its pending requests.
  await page.evaluate((url) => {
    history.pushState({}, '', url)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, path)
}
async function settled(page) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await page.waitForTimeout(200) // allow a wrongly accepted response to trigger its document request
}

try {
  for (const kind of ['works', 'projects']) {
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const prefix = kind === 'works' ? 'wrk' : 'prj'
    const a = `${prefix}_race_a`, b = `${prefix}_race_b`
    const record = kind === 'works' ? work : project
    const shown = kind === 'works' ? document : chapter
    const waitingA = [], gotA = deferred(), gotPoll = deferred()
    let phase = 'navigation', polls = 0
    await page.route(new RegExp(`/api/${kind}/${prefix}_race_[ab](?:[/?]|$)`), async (route) => {
      const url = new URL(route.request().url())
      const id = url.pathname.split('/')[3]
      const suffix = url.pathname.split('/').slice(4).join('/')
      assert.equal(route.request().method(), 'GET', 'the race test must not start or alter a job')
      if (suffix) {
        assert.ok(suffix === 'document' || suffix === 'chapters/1', `unexpected endpoint ${suffix}`)
        await route.fulfill({ json: shown(id, Number(url.searchParams.get('version') || 1)) })
      } else if (id === a) {
        waitingA.push(route)
        gotA.resolve()
      } else if (phase === 'polling' && ++polls === 1) {
        gotPoll.resolve(route) // keep the first refresh waiting; the second returns first
      } else {
        await route.fulfill({ json: record(b, phase === 'polling' ? 2 : 1, phase !== 'polling') })
      }
    })
    await page.goto(`${base}/app/${kind}/${a}`)
    await gotA.promise
    await navigate(page, `/app/${kind}/${b}`)
    await page.getByText(body(b, 1), { exact: true }).waitFor()
    for (const route of waitingA) await route.fulfill({ json: record(a, 1, false) })
    await settled(page)
    assert.equal(await page.getByText(body(b, 1), { exact: true }).count(), 1, 'late A replaced selected B')
    assert.equal(await page.getByText(body(a, 1), { exact: true }).count(), 0)

    phase = 'polling'
    const oldPoll = await gotPoll.promise
    await page.getByText(body(b, 2), { exact: true }).waitFor()
    await oldPoll.fulfill({ json: record(b, 1, false) })
    await settled(page)
    assert.equal(await page.getByText(body(b, 2), { exact: true }).count(), 1, 'late refresh restored version one')
    assert.equal(await page.getByText(body(b, 1), { exact: true }).count(), 0)
    assert.deepEqual(errors, [])
    console.log(`PASS ${kind}: navigation and reversed polling responses preserve the selected document`)
    await page.close()
  }
} finally {
  await browser.close()
}
