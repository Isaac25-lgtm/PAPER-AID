// Audit diagnostics for the isolated TEST backend on 8001 and test frontend on 5001.
// Passing means the current defects are reproduced. Never run against production.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'
const base = 'http://localhost:5001'
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext()
const page = await context.newPage()
const headers = { Authorization: 'Dev demo@paperaid.app' }
const details = { inputs: { topic:'Malaria vaccine uptake in Mukono', level:'MASTERS', programme:'Master of Public Health', studyArea:'Mukono District' } }
const api = async (path, data) => {
  const res = data === undefined ? await context.request.get(base+path,{headers}) : await context.request.post(base+path,{headers,data})
  assert.equal(res.status(),200,await res.text())
  return res.json()
}
try {
  await page.goto(base+'/sign-in')
  await page.getByLabel('Email').fill('demo@paperaid.app')
  await page.getByLabel('Password').fill('audit-password')
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await page.waitForURL(/\/app/)
  const p = await api('/api/projects',details)
  const q = await api(`/api/projects/${p.id}/steps`,{step:'PLAN'})
  await api(`/api/projects/${p.id}/steps/${q.job.id}/submit`,{quoteId:q.quote.id})
  for (let i=0;i<100;i++) {
    const j=await api(`/api/jobs/${q.job.id}`)
    if(j.status==='COMPLETED') break
    assert.notEqual(j.status,'FAILED')
    await new Promise(r=>setTimeout(r,100))
  }
  const initial = await api(`/api/projects/${p.id}`)
  await page.goto(base+`/app/projects/${p.id}`)
  await page.getByLabel('Title',{exact:true}).waitFor()
  await page.getByLabel('Title',{exact:true}).fill('My unsaved title edit')
  await page.getByRole('button',{name:'See the price',exact:true}).click()
  let changed
  await page.route('**/api/projects/*/steps/*/submit',async route=>{
    const response = await route.fetch()
    assert.equal(response.status(),200,await response.text())
    const current = await api(`/api/projects/${p.id}`)
    changed = await api(`/api/projects/${p.id}/plan`,{baseVersion:current.planVersion,plan:{...current.plan,problem:'A new problem saved elsewhere must be preserved.'}})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Start',exact:true}).click()
  // A server edit arrives while the old local editor is dirty and the new step runs.
  await page.getByText('Step finished',{exact:true}).waitFor({timeout:30000})
  await page.getByText(`Plan version ${changed.planVersion}`,{exact:true}).waitFor()
  assert.notEqual(await page.getByLabel('Problem (the core of your problem statement)').inputValue(),'A new problem saved elsewhere must be preserved.')
  await page.getByRole('button',{name:'Save changes',exact:true}).first().click()
  await page.getByText(`Plan version ${changed.planVersion+1}`,{exact:true}).waitFor()
  const overwritten = await api(`/api/projects/${p.id}`)
  assert.equal(overwritten.plan.title,'My unsaved title edit')
  assert.equal(overwritten.plan.problem,initial.plan.problem)
  console.log('EDITOR: dirty plan used the newer version number and silently overwrote a concurrent saved problem.')

  const loadPage = await context.newPage()
  await loadPage.route(`**/api/projects/${p.id}`,r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'AUDIT_PROJECT_LOAD_FAILURE'})}))
  await Promise.all([loadPage.waitForResponse(r=>r.url().endsWith('/api/projects/'+p.id)&&r.status()===503),loadPage.goto(base+`/app/projects/${p.id}`)])
  await loadPage.waitForTimeout(500)
  assert.equal(await loadPage.getByText('AUDIT_PROJECT_LOAD_FAILURE').count(),0)
  assert.ok(await loadPage.locator('.animate-pulse').count()>0)
  console.log('LOAD: a 503 response leaves only the loading skeleton; the saved error is invisible.')

  const progressPage = await context.newPage()
  let polls=0
  await progressPage.route(`**/api/projects/${p.id}`,r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...overwritten,activeJob:'job_audit_blocked'})}))
  await progressPage.route('**/api/jobs/job_audit_blocked',r=>{polls++;return r.fulfill({status:403,contentType:'application/json',body:JSON.stringify({message:'AUDIT_APPCHECK_UNAVAILABLE'})})})
  await progressPage.goto(base+`/app/projects/${p.id}`)
  await progressPage.getByText('Queued',{exact:true}).waitFor()
  await progressPage.waitForTimeout(300)
  const initialPolls = polls // development StrictMode mounts the watcher twice
  await progressPage.waitForTimeout(4500)
  assert.ok(initialPolls > 0)
  assert.equal(polls,initialPolls)
  assert.equal(await progressPage.getByText('AUDIT_APPCHECK_UNAVAILABLE').count(),0)
  assert.equal(await progressPage.getByText('Queued',{exact:true}).count(),1)
  console.log('PROGRESS: a 403 stops further polling, with no error; the step still appears queued.')
} finally { await browser.close() }
