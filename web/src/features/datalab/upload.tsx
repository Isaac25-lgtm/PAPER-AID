import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Checkbox, Select } from '../../components/ui/field'
import { FileDropzone } from '../../components/ui/file-dropzone'
import { Alert, Card } from '../../components/ui/primitives'
import type { IdentifierRules, UploadChoice } from '../../lib/datalab-types'
import { useData } from '../../lib/data'

interface Flagged {
  index: number
  name: string
  why: string
}

/** Finds the separator from the header line (the same separators the server reads). */
function separatorOf(text: string): string {
  const line = text.slice(0, text.indexOf('\n') > 0 ? text.indexOf('\n') : undefined)
  return [',', ';', '\t', '|'].map((s) => [s, line.split(s).length] as const).sort((a, b) => b[1] - a[1])[0][0]
}

/** A CSV read in full (quotes, doubled quotes and line breaks inside quotes included). */
export function parseCsv(text: string, sep: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"'
        i++
      } else if (c === '"') quoted = false
      else cell += c
    } else if (c === '"') quoted = true
    else if (c === sep) {
      row.push(cell)
      cell = ''
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += c
  }
  if (cell !== '' || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows.filter((r) => r.some((x) => x.trim() !== ''))
}

function toCsv(rows: string[][], sep: string): string {
  const quote = (v: string) => (/["\r\n]/.test(v) || v.includes(sep) ? `"${v.replace(/"/g, '""')}"` : v)
  return rows.map((r) => r.map(quote).join(sep)).join('\n') + '\n'
}

/** The columns the shared rules flag: by name, or because most of their values look like emails, phone or ID numbers. */
export function flagColumns(rows: string[][], rules: IdentifierRules): Flagged[] {
  const [header, ...body] = rows
  const headers = Object.entries(rules.headers).map(([kind, p]) => [kind, new RegExp(p, 'i')] as const)
  const values = Object.entries(rules.values).map(([kind, p]) => [kind, new RegExp(p, 'i')] as const)
  const out: Flagged[] = []
  header.forEach((name, index) => {
    const exception = rules.except?.[`PERSONAL`] ? new RegExp(rules.except.PERSONAL, 'i') : null
    const byName = headers.find(([kind, re]) => re.test(name) && !(kind === 'PERSONAL' && exception?.test(name)))
    if (byName) return out.push({ index, name, why: rules.labels[byName[0]] ?? byName[0] })
    const present = body.map((r) => (r[index] ?? '').trim()).filter((v) => v !== '')
    if (!present.length) return
    const byValue = values.find(([, re]) => present.filter((v) => re.test(v)).length / present.length > rules.share)
    if (byValue) out.push({ index, name, why: rules.labels[byValue[0]] ?? byValue[0] })
  })
  return out
}

/** The upload, with the researcher's confirmations, the data's country and, for a CSV, the columns
 *  removed in the browser so that they never reach PaperAid (owner decision 2026-10-04). */
export function UploadCard({ retentionDays, busy, onUpload, compact = false, onCancel }: {
  retentionDays: number
  busy: boolean
  onUpload: (file: File, choice: UploadChoice) => void
  compact?: boolean
  onCancel?: () => void
}) {
  const data = useData()
  const [countries, setCountries] = useState<{ iso3: string; name: string; available: boolean }[]>([])
  const [rules, setRules] = useState<IdentifierRules | null>(null)
  const [country, setCountry] = useState('UGA')
  const [mayUse, setMayUse] = useState(false)
  const [identifiers, setIdentifiers] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [scan, setScan] = useState<{ rows: string[][]; sep: string; flagged: Flagged[] } | null>(null)
  const [remove, setRemove] = useState<number[]>([])
  const [reading, setReading] = useState(false)
  useEffect(() => {
    data.datalab.countries().then(setCountries).catch(() => setCountries([{ iso3: 'UGA', name: 'Uganda', available: true }]))
    data.datalab.identifierRules().then(setRules).catch(() => setRules(null))
  }, [data])
  const chosen = countries.find((c) => c.iso3 === country)
  const csv = Boolean(file && /\.(csv|txt|tsv)$/i.test(file.name))

  const pick = async (f: File) => {
    setFile(f)
    setScan(null)
    setRemove([])
    if (!rules || !/\.(csv|txt|tsv)$/i.test(f.name)) return
    setReading(true)
    try {
      const text = await f.text()
      const sep = separatorOf(text)
      const rows = parseCsv(text, sep)
      if (rows.length < 2) return
      const flagged = flagColumns(rows, rules)
      setScan({ rows, sep, flagged })
      setRemove(flagged.map((x) => x.index))
    } finally {
      setReading(false)
    }
  }

  const send = () => {
    if (!file) return
    let upload = file
    let removed: string[] = []
    if (scan && remove.length) {
      const kept = scan.rows.map((r) => r.filter((_, i) => !remove.includes(i)))
      upload = new File([toCsv(kept, scan.sep)], file.name, { type: 'text/csv' })
      removed = scan.flagged.filter((x) => remove.includes(x.index)).map((x) => `"${x.name}" (${x.why})`)
    }
    onUpload(upload, { country, consent: true, removed })
  }

  return (
    <Card className="space-y-4 p-6">
      {!compact && <h2 className="text-lg font-semibold">Upload your data</h2>}
      <Select label="Which country is this data from?" value={country} onChange={(e) => setCountry(e.target.value)}>
        {countries.map((c) => <option key={c.iso3} value={c.iso3}>{c.name}</option>)}
      </Select>
      {chosen && !chosen.available && (
        <Alert tone="warning">
          Data Lab isn't available yet for data from {chosen.iso3 === 'OTHER' ? 'this country' : chosen.name}. {chosen.iso3 === 'OTHER' ? 'Its' : `${chosen.name}'s`} data
          protection law sets rules on how personal data is handled, and we're making sure PaperAid meets them before we offer this. Data from Uganda works as normal.
        </Alert>
      )}
      <FileDropzone label="Your dataset" hint="CSV or Excel (.xlsx), up to 20 MB. The first row should hold the column names." accept=".csv,.xlsx,.tsv,.txt" onFile={(f) => void pick(f)} disabled={busy} />
      {file && <p className="text-sm text-fg">Chosen: <span className="font-medium">{file.name}</span></p>}
      {reading && <p className="flex items-center gap-2 text-sm text-fg-muted"><Loader2 className="size-4 animate-spin" aria-hidden /> Checking your file on this device…</p>}
      {scan && scan.flagged.length > 0 && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <p className="text-sm font-medium text-fg">These columns may identify people or places. Ticked ones are removed on this device, before your file is sent:</p>
          {scan.flagged.map((x) => (
            <Checkbox key={x.index} label={`"${x.name}" (${x.why})`} checked={remove.includes(x.index)}
              onChange={(e) => setRemove(e.target.checked ? [...remove, x.index] : remove.filter((i) => i !== x.index))} />
          ))}
          <p className="text-xs text-fg-muted">PaperAid checks names, phone numbers, email addresses, ID numbers and coordinates it recognises. It can't promise to find every identifier.</p>
        </div>
      )}
      {scan && scan.flagged.length === 0 && <p className="text-sm text-fg-muted">PaperAid found no column that looks like names, phone numbers, ID numbers or coordinates.</p>}
      {file && !csv && (
        <p className="text-sm text-fg-muted">Excel files are checked after upload: columns that may identify people or places are left out of the analysis. To keep them off PaperAid entirely, delete them first or save the sheet as CSV.</p>
      )}
      <div className="space-y-2 rounded-xl border border-line p-4">
        <p className="text-sm font-medium text-fg">Before you upload, please confirm:</p>
        <Checkbox checked={mayUse} onChange={(e) => setMayUse(e.target.checked)} label="I have the right to use this data for this analysis (my participants' consent, and ethics approval where my study needs it)." />
        <Checkbox checked={identifiers} onChange={(e) => setIdentifiers(e.target.checked)} label="I have removed names, phone numbers and ID numbers, or I'll let PaperAid remove or leave out the columns it recognises." />
        <p className="text-xs text-fg-subtle">PaperAid uses this data only to produce your results and deletes it {retentionDays} days after your last change. Your original file stays on your device.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} disabled={!file || reading || !mayUse || !identifiers || !chosen?.available} onClick={send}>Upload</Button>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </Card>
  )
}
