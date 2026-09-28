// Read-only browser diagnostics against the isolated 5001/8001 stack.
// PASS means the bug was reproduced, not repaired. Network fixtures are synthetic.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
const { chromium } = createRequire(new URL('../web/package.json', import.meta.url))('playwright-core')
const base = process.env.PAPERAID_AUDIT_BASE ?? 'http://127.0.0.1:5000'
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext()
await context.addInitScript(() => localStorage.setItem('paperaid.local-user.v2', JSON.stringify({email:'demo@paperaid.app',displayName:'Audit'})))
const headers = { Authorization: 'Dev demo@paperaid.app' }
const api = async (path, data) => {
  const res = await context.request[data === undefined ? 'get' : 'post'](base + path, { headers, ...(data === undefined ? {} : {data}) })
  assert.equal(res.status(), 200, await res.text())
  return res.json()
}
try {
  const page = await context.newPage()
  const project = await api('/api/projects', { inputs:{topic:'Audit synthetic study in Mukono District',level:'MASTERS',programme:'Public Health'} })
  project.planStatus = 'APPROVED'
  const state = project.chapters.find(c=>c.number===1)
  state.current = 1
  state.approved = false
  state.versions = [1,2].map(v=>({version:v,jobId:`job_seed${v}`,words:100,planVersion:1,createdAt:project.createdAt,note:'',passed:0,total:0}))
  const chapter = {number:1,title:'Synthetic chapter',version:1,planVersion:1,sections:[{key:'background',number:'1.0',heading:'Background',paragraphs:['VERSION ONE visible text'],table:null,tableCaption:'',needsReview:false}],readiness:[],warnings:[],words:100,references:[],framework:[]}
  await page.route(`**/api/projects/${project.id}`, r=>r.fulfill({json:project}))
  await page.route(`**/api/projects/${project.id}/chapters/1?*`, r=> {
    const version = new URL(r.request().url()).searchParams.get('version')
    return version === '2' ? r.fulfill({status:503,json:{message:'CHAPTER_TWO_LOAD_FAILED'}}) : r.fulfill({json:chapter})
  })
  let submitted = null
  await page.route(`**/api/projects/${project.id}/chapters/1`, async r=> {
    submitted = r.request().postDataJSON()
    await r.fulfill({json:project})
  })
  await page.goto(`${base}/app/projects/${project.id}`)
  await page.getByRole('tab', {name:'Chapter 1',exact:true}).click()
  await page.getByText('VERSION ONE visible text',{exact:true}).waitFor()
  await page.getByLabel('Version',{exact:true}).selectOption('2')
  await page.getByText('CHAPTER_TWO_LOAD_FAILED',{exact:true}).waitFor()
  assert.equal(await page.getByText('VERSION ONE visible text',{exact:true}).count(),1)
  const saved = page.waitForResponse(r=>r.url().endsWith(`/api/projects/${project.id}/chapters/1`) && r.request().method()==='POST')
  await page.getByRole('button',{name:'Use this version',exact:true}).click()
  await saved
  assert.equal(submitted.version,2)
  console.log('REPRODUCED: selector says version 2, preview still shows version 1 after a 503, and Use this version selects unseen version 2.')

  const workspace = await context.newPage()
  const job = await api('/api/jobs', {})
  job.status = 'COMPLETED'
  job.outcome = 'FULL'
  job.selection.writing = 'REDRAFT'
  job.analysis = {band:'LOW',confidence:'HIGH',analysedWords:100,excludedWords:0,findings:[],review:[],algorithmVersion:'audit',method:''}
  const change = {blockId:'g00001',section:'Body',before:'ORIGINAL FIRST PARAGRAPH\nORIGINAL SECOND PARAGRAPH',after:'REWRITTEN GROUP',reason:'Clearer',kept:false}
  job.refinement = {mode:'REDRAFT',targetedBlocks:1,refinedBlocks:1,keptOriginal:0,untouchedBlocks:0,changes:[change],method:'',trimmed:false}
  job.rejectedChanges = []
  const doc = {format:'DOCX',blocks:[{id:'b00001',kind:'paragraph',text:'ORIGINAL FIRST PARAGRAPH',section:'Body',level:null,editable:true},{id:'b00002',kind:'paragraph',text:'ORIGINAL SECOND PARAGRAPH',section:'Body',level:null,editable:true}],groups:{g00001:['b00001','b00002']},changes:[change]}
  await workspace.route(`**/api/jobs/${job.id}`, r=>r.fulfill({json:job}))
  await workspace.route(`**/api/jobs/${job.id}/document`,r=>r.fulfill({json:doc}))
  await workspace.route(`**/api/jobs/${job.id}/changes/g00001`,r=>{job.rejectedChanges=['g00001'];return r.fulfill({json:job})})
  await workspace.goto(`${base}/app/jobs/${job.id}`)
  await workspace.getByRole('button',{name:'Keep my wording',exact:true}).click()
  const article = workspace.locator('article')
  await article.getByText('ORIGINAL FIRST PARAGRAPH',{exact:true}).waitFor()
  assert.equal(await article.getByText('ORIGINAL SECOND PARAGRAPH',{exact:true}).count(),0)
  console.log('REPRODUCED: rejecting a two-paragraph Deep Redraft group restores only its first original paragraph in the paper preview.')
} finally {
  await browser.close()
}
