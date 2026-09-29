// Browser regressions for Codex's audit of 56c4f83 (M25, M26), from its diagnostic script with the
// assertions turned to the correct behaviour. Network responses are synthetic; run against the
// web dev server (:5000) and the browser-test backend (python -m tests.serve_e2e).
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const base = process.env.PAPERAID_BASE ?? 'http://localhost:5000'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext()
await context.addInitScript(() => localStorage.setItem('paperaid.local-user.v2', JSON.stringify({ email: 'demo@paperaid.app', displayName: 'Audit' })))
const headers = { Authorization: 'Dev demo@paperaid.app' }
const api = async (path, data) => {
  const res = await context.request[data === undefined ? 'get' : 'post'](base + path, { headers, ...(data === undefined ? {} : { data }) })
  assert.equal(res.status(), 200, await res.text())
  return res.json()
}
let failed = false
try {
  // M26: a chapter version that fails to load never shows the previous one, and cannot be chosen unseen.
  const page = await context.newPage()
  const project = await api('/api/projects', { inputs: { topic: 'Audit synthetic study in Mukono District', level: 'MASTERS', programme: 'Public Health' } })
  project.planStatus = 'APPROVED'
  const state = project.chapters.find((c) => c.number === 1)
  state.current = 1
  state.approved = false
  state.versions = [1, 2].map((v) => ({ version: v, jobId: `job_seed${v}`, words: 100, planVersion: 1, createdAt: project.createdAt, note: '', passed: 0, total: 0 }))
  const chapter = { number: 1, title: 'Synthetic chapter', version: 1, planVersion: 1, sections: [{ key: 'background', number: '1.0', heading: 'Background', paragraphs: ['VERSION ONE visible text'], table: null, tableCaption: '', needsReview: false }], readiness: [], warnings: [], words: 100, references: [], framework: [] }
  await page.route(`**/api/projects/${project.id}`, (r) => r.fulfill({ json: project }))
  await page.route(`**/api/projects/${project.id}/chapters/1?*`, (r) => {
    const version = new URL(r.request().url()).searchParams.get('version')
    return version === '2' ? r.fulfill({ status: 503, json: { message: 'CHAPTER_TWO_LOAD_FAILED' } }) : r.fulfill({ json: chapter })
  })
  await page.goto(`${base}/app/projects/${project.id}`)
  await page.getByRole('tab', { name: 'Chapter 1', exact: true }).click()
  await page.getByText('VERSION ONE visible text', { exact: true }).waitFor()
  await page.getByLabel('Version', { exact: true }).selectOption('2')
  await page.getByText('CHAPTER_TWO_LOAD_FAILED', { exact: true }).waitFor()
  assert.equal(await page.getByText('VERSION ONE visible text', { exact: true }).count(), 0, 'the previous version is still shown')
  assert.equal(await page.getByRole('button', { name: 'Use this version', exact: true }).isDisabled(), true, 'an unloaded version can be chosen')
  await page.getByRole('button', { name: 'Try again' }).waitFor()
  console.log('✓ M26: a failed version load shows its error with a retry, no stale content, and cannot be chosen')

  state.current = 2
  await page.reload()
  await page.getByRole('tab', { name: 'Chapter 1', exact: true }).click()
  await page.getByLabel('Version', { exact: true }).selectOption('1')
  await page.getByText('VERSION ONE visible text', { exact: true }).waitFor()
  await page.getByText(/Changes are made to the current version/).waitFor()
  assert.equal(await page.getByLabel('What should change in Chapter 1?').count(), 0)
  console.log('✓ historical chapters cannot submit change requests against another version')

  project.profileMissing = true
  project.rulebook = 'custom-missing'
  let restored = false
  await page.route(`**/api/projects/${project.id}/rulebook/default`, (r) => {
    restored = true
    project.profileMissing = false
    project.rulebook = 'ucu-2018-v1'
    return r.fulfill({ json: project })
  })
  await page.reload()
  await page.getByRole('tab', { name: 'Details', exact: true }).click()
  await page.getByRole('button', { name: 'Use the standard structure', exact: true }).click()
  await page.getByText('Your chapters follow this structure; it stays the same for this proposal.', { exact: true }).waitFor()
  assert.ok(restored, 'missing-profile recovery did not call the restoration endpoint')
  console.log('✓ a missing institution profile can be restored after chapters exist')

  // M25: rejecting a Deep Redraft group shows every original paragraph again.
  const workspace = await context.newPage()
  const job = await api('/api/jobs', {})
  job.status = 'COMPLETED'
  job.outcome = 'FULL'
  job.selection.writing = 'REDRAFT'
  job.analysis = { band: 'LOW', confidence: 'HIGH', analysedWords: 100, excludedWords: 0, findings: [], review: [], algorithmVersion: 'audit', method: '' }
  const change = { blockId: 'g00001', section: 'Body', before: 'ORIGINAL FIRST PARAGRAPH\nORIGINAL SECOND PARAGRAPH', after: 'REWRITTEN GROUP', reason: 'Clearer', kept: false }
  job.refinement = { mode: 'REDRAFT', targetedBlocks: 1, refinedBlocks: 1, keptOriginal: 0, untouchedBlocks: 0, changes: [change], method: '', trimmed: false }
  job.rejectedChanges = []
  const doc = {
    format: 'DOCX',
    blocks: [
      { id: 'b00001', kind: 'paragraph', text: 'ORIGINAL FIRST PARAGRAPH', section: 'Body', level: null, editable: true },
      { id: 'b00002', kind: 'paragraph', text: 'ORIGINAL SECOND PARAGRAPH', section: 'Body', level: null, editable: true },
    ],
    groups: { g00001: ['b00001', 'b00002'] },
    changes: [change],
  }
  await workspace.route(`**/api/jobs/${job.id}`, (r) => r.fulfill({ json: job }))
  await workspace.route(`**/api/jobs/${job.id}/document`, (r) => r.fulfill({ json: doc }))
  await workspace.route(`**/api/jobs/${job.id}/changes/g00001`, (r) => {
    job.rejectedChanges = ['g00001']
    return r.fulfill({ json: job })
  })
  await workspace.goto(`${base}/app/jobs/${job.id}`)
  const article = workspace.locator('article')
  await article.getByText('REWRITTEN GROUP', { exact: true }).waitFor()
  assert.equal(await article.getByText('ORIGINAL SECOND PARAGRAPH', { exact: true }).count(), 0, 'the kept rewrite still shows the replaced paragraph')
  await workspace.getByRole('button', { name: 'Keep my wording', exact: true }).click()
  await article.getByText('ORIGINAL FIRST PARAGRAPH', { exact: true }).waitFor()
  await article.getByText('ORIGINAL SECOND PARAGRAPH', { exact: true }).waitFor()
  assert.equal(await article.getByText('REWRITTEN GROUP', { exact: true }).count(), 0)
  console.log('✓ M25: rejecting a redrafted group restores every original paragraph')
  job.analysisAfter = { ...job.analysis, band: 'LOW', percent: null }
  doc.percent = 33
  doc.percentAfter = 9
  await workspace.reload()
  await workspace.locator('aside').getByText('9%', { exact: true }).waitFor()
  await workspace.locator('aside').getByText('33%', { exact: true }).waitFor()
  console.log('✓ recovered before and after percentages render on an older refined result')
} catch (e) {
  failed = true
  console.error(`audit journey failed: ${e.message}`)
} finally {
  await browser.close()
}
if (failed) process.exit(1)
console.log('audit browser checks passed')
