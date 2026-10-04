// Private-mode spike (owner decision 2026-10-04, Codex's go/no-go): can Data Lab's own Python engine run in a
// phone's browser? Chrome emulates a mid-range Android phone (390×844, 4× slower CPU, 4G at ~9 Mbit/s), loads
// Pyodide and the real engine (backend/app/datalab), and measures: download size, start-up time, reading and
// profiling a ~20 MB CSV, cleaning proposals, the statistics (checked against the server's numbers), small-count
// protection, a chart, a district map, the report workbook and a Word file, and memory. PDF can't be measured:
// the server makes PDFs with LibreOffice, which can't run in a browser. Nothing here is shipped to users.
// Usage: node scripts/spike-private-mode.mjs [out.json]
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { chromium } from 'playwright-core'

const backend = resolve(import.meta.dirname, '../../backend')
const out = process.argv[2] ?? 'spike-private-mode.json'
const executablePath = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.2/full/'

// The engine's files, as the browser would receive them in a packaged bundle.
const files = {}
const add = (rel) => (files[rel] = readFileSync(join(backend, rel), 'utf-8'))
for (const rel of ['app/__init__.py', 'app/core/__init__.py', 'app/core/errors.py', 'app/jobs/__init__.py', 'app/jobs/models.py', 'app/formatting/__init__.py',
  'app/formatting/presets.py', 'app/datalab/__init__.py', 'app/datalab/models.py', 'app/datalab/report.py', 'app/datalab/workbook.py']) add(rel)
for (const name of readdirSync(join(backend, 'app/datalab/engine'))) if (name.endsWith('.py') || name.endsWith('.json')) add(`app/datalab/engine/${name}`)
for (const name of ['uganda_districts_2020.geojson', 'uganda_districts_2020.json', 'uganda_subregions.json', 'uganda_water_dcw.geojson']) add(`app/datalab/geo/${name}`)
const engineBytes = Object.values(files).reduce((n, s) => n + Buffer.byteLength(s), 0)

const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
  userAgent: 'Mozilla/5.0 (Linux; Android 13; Pixel 6a) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36' })
const page = await context.newPage()
const cdp = await context.newCDPSession(page)
await cdp.send('Network.enable')
await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 })
await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (9 * 1024 * 1024) / 8, uploadThroughput: (3 * 1024 * 1024) / 8 })
let downloaded = 0
cdp.on('Network.loadingFinished', (e) => (downloaded += e.encodedDataLength))
const problems = []
page.on('pageerror', (e) => problems.push(e.message))
await page.goto('about:blank')
const result = await page.evaluate(async ({ PYODIDE, files }) => {
  const t = () => performance.now()
  const timings = {}
  const time = async (name, fn) => {
    const start = t()
    const value = await fn()
    timings[name] = Math.round(t() - start) / 1000
    return value
  }
  await time('download Pyodide', () => new Promise((ok, fail) => {
    const s = document.createElement('script')
    s.src = PYODIDE + 'pyodide.js'
    s.onload = ok
    s.onerror = fail
    document.head.appendChild(s)
  }))
  const py = await time('start Pyodide', () => globalThis.loadPyodide({ indexURL: PYODIDE }))
  await time('load scientific packages', () => py.loadPackage(['numpy', 'pandas', 'scipy', 'matplotlib', 'shapely', 'pydantic', 'lxml', 'micropip']))
  const extra = await time('install pure-Python packages', async () => {
    const micropip = py.pyimport('micropip')
    const installed = []
    for (const name of ['openpyxl', 'xlsxwriter', 'python-docx', 'geopandas']) {
      try {
        await micropip.install(name)
        installed.push(name)
      } catch (e) {
        installed.push(`${name}: ${String(e).slice(0, 160)}`)
      }
    }
    return installed
  })
  await time('write the engine', async () => {
    for (const [path, text] of Object.entries(files)) {
      const dir = '/home/pyodide/' + path.split('/').slice(0, -1).join('/')
      py.FS.mkdirTree(dir)
      py.FS.writeFile('/home/pyodide/' + path, text)
    }
  })
  const steps = {}
  const run = async (name, code) => {
    const start = t()
    try {
      const value = await py.runPythonAsync(code)
      steps[name] = { seconds: Math.round(t() - start) / 1000, value: value?.toJs ? value.toJs() : value }
    } catch (e) {
      steps[name] = { seconds: Math.round(t() - start) / 1000, error: String(e).split('\n').slice(-3).join(' ').slice(0, 300) }
    }
  }
  await run('import the engine', `
import sys; sys.path.insert(0, "/home/pyodide")
from app.datalab.engine import ingest, profile, clean, stats, disclosure, charts
from app.datalab.models import AnalysisSpec
"ok"`)
  await run('make a ~20 MB CSV (test data)', `
import numpy as np
rng = np.random.default_rng(1)
D = ["Gulu", "Pader", "Kitgum", "Lira", "Mbarara", "Kabale", "Jinja", "Mbale", "Arua", "Hoima"]
lines = ["id,district,sex,age,income,score,passed,household,education,water,distance,notes"]
n = 200_000
sexes = np.where(rng.random(n) < .5, "Male", "Female"); ages = 18 + (rng.random(n) * 60).astype(int); inc = rng.gamma(2, 200000, n).astype(int)
score = rng.normal(60, 12, n); passed = np.where(rng.random(n) < .6, "yes", "no"); hh = 1 + (rng.random(n) * 9).astype(int); dist = rng.random(n) * 5
for i in range(n):
    lines.append(f"{i:07d},{D[i % 10]},{sexes[i]},{ages[i]},{inc[i]},{score[i]:.1f},{passed[i]},{hh[i]},{['None','Primary','Secondary','Tertiary'][i % 4]},{['Borehole','Tap','Spring','River'][i % 4]},{dist[i]:.2f},ok")
DATA = ("\\n".join(lines) + "\\n").encode()
len(DATA) / 2**20`)
  await run('read the file', `
LIMITS = ingest.Limits(rows=200_000, columns=300, cells=6_000_000, expanded_bytes=120 * 2**20)
table = ingest.read(DATA, "d.csv", None, LIMITS); len(table.rows)`)
  await run('profile the variables', `frame, variables = profile.infer(table); by = {v.name: v for v in variables}; [v.stored for v in variables].count("number")`)
  await run('cleaning proposals', `len(clean.proposals(frame, variables))`)
  await run('describe (district)', `ctx = stats.Context(frame, by, 1); r = stats.run(ctx, AnalysisSpec(kind="DESCRIBE", variables=["district"])); r.statistics["n"]`)
  await run('cross-tabulation', `r = stats.run(ctx, AnalysisSpec(kind="CROSSTAB", variables=["district", "education"])); round(r.statistics["chi2"], 4)`)
  await run('two groups (Welch)', `r2 = stats.run(ctx, AnalysisSpec(kind="COMPARE_TWO", variables=["score", "sex"], method="MEANS")); round(r2.statistics["t"], 6)`)
  await run('correlation (Spearman)', `r3 = stats.run(ctx, AnalysisSpec(kind="CORRELATE", variables=["age", "score"], method="SPEARMAN")); round(r3.statistics["r"], 6)`)
  await run('reference check: R sleep data (Welch t = -1.860813)', `
import pandas as pd
S1 = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0.0, 2.0]; S2 = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4]
t2 = ingest.Table(columns=["extra", "group"], rows=[[a, b] for a, b in zip(S1 + S2, ["1"] * 10 + ["2"] * 10)])
f2, v2 = profile.infer(t2); rr = stats.run(stats.Context(f2, {v.name: v for v in v2}, 1), AnalysisSpec(kind="COMPARE_TWO", variables=["extra", "group"], method="MEANS"))
round(rr.statistics["t"], 6)`)
  await run('small-count protection', `g = disclosure.protect(np.array([[1, 0], [20, 30]]), 5); bool(g.cells[0, 0] and g.rows[0])`)
  await run('a chart (PNG)', `len(charts.for_result(r2, frame, 5))`)
  await run('a district map (PNG)', `
from app.datalab.engine import maps
res, png = maps.run(ctx, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT")); len(png)`)
  await run('report workbook (Excel)', `
from app.datalab import workbook
len(workbook.build("Spike", "d.csv", 1, len(frame), 5, variables, [], [r, r2], lambda p: None))`)
  await run('Word file', `
from docx import Document; import io
doc = Document(); doc.add_heading("Spike", 1); [doc.add_paragraph("A paragraph of results.") for _ in range(200)]
b = io.BytesIO(); doc.save(b); len(b.getvalue())`)
  const memory = { wasmHeapMiB: Math.round(py._module.HEAP8.length / 2 ** 20), jsHeapMiB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 2 ** 20) : null }
  return { timings, steps, extra, memory }
}, { PYODIDE, files })
result.downloadedMiB = Math.round((downloaded / 2 ** 20) * 10) / 10
result.engineFilesMiB = Math.round((engineBytes / 2 ** 20) * 10) / 10
result.problems = problems
result.emulated = 'Chrome mobile emulation: 390×844 @3x, CPU slowed 4×, 4G (9 Mbit/s down, 150 ms latency). Not a real phone.'
writeFileSync(out, JSON.stringify(result, null, 2))
console.log(JSON.stringify(result, null, 2))
await browser.close()
