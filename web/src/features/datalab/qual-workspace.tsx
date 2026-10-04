import { Download, FileSpreadsheet, Loader2, Sparkles, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button } from '../../components/ui/button'
import { Checkbox, Input, Select, TextArea } from '../../components/ui/field'
import { Alert, Card } from '../../components/ui/primitives'
import type { DataProject, ReportDocument } from '../../lib/datalab-types'
import { DataError, useData } from '../../lib/data'
import { useTitle } from '../../lib/use-title'
import { ReportView } from './parts'

/** "Agnes Akello = Participant A" lines → pairs; a line without "=" gets a code of its own. */
function pairs(text: string): [string, string][] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => {
      const [name, code] = line.split('=').map((x) => x.trim())
      return [name, code || `Participant ${String.fromCharCode(65 + (i % 26))}`] as [string, string]
    })
}

/** A qualitative Data Lab project on one page (owner decision 2026-10-04): the question, the transcripts, the analysis. */
export function QualWorkspace({ initial }: { initial: DataProject }) {
  const data = useData()
  const navigate = useNavigate()
  const [project, setProject] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [countries, setCountries] = useState<{ iso3: string; name: string; available: boolean }[]>([])
  const [mode, setMode] = useState<'file' | 'paste'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [label, setLabel] = useState('')
  const [names, setNames] = useState('')
  const [country, setCountry] = useState('UGA')
  const [agreed, setAgreed] = useState(false)
  const [report, setReport] = useState<ReportDocument | null>(null)
  useTitle(project.title)

  const load = useCallback(async () => {
    const p = await data.datalab.get(project.id)
    if (p) setProject(p)
  }, [data, project.id])

  useEffect(() => {
    data.datalab.countries().then(setCountries).catch(() => setCountries([{ iso3: 'UGA', name: 'Uganda', available: true }]))
  }, [data])
  useEffect(() => {
    if (!project.activeJob) return
    const timer = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(timer)
  }, [project.activeJob, load])
  useEffect(() => {
    if (!project.reports.length) return
    data.datalab.report(project.id).then(setReport).catch(() => setReport(null))
  }, [data, project.id, project.reportCurrent, project.reports.length])

  const act = async (fn: () => Promise<DataProject | void>) => {
    setBusy(true)
    setError(null)
    try {
      const next = await fn()
      if (next) setProject(next)
      return true
    } catch (e) {
      setError(e instanceof DataError ? e.message : 'That did not work. Try again.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const add = async () => {
    const choice = { label: label.trim(), consent: agreed, country, replace: pairs(names) }
    const ok = await act(() => (mode === 'file' && file ? data.datalab.addDocument(project.id, file, choice) : data.datalab.addText(project.id, text, choice)))
    if (ok) {
      setFile(null)
      setText('')
      setLabel('')
    }
  }

  const chosen = countries.find((c) => c.iso3 === country)
  const words = project.documents.reduce((n, d) => n + d.words, 0)
  const name = project.title || 'Qualitative analysis'
  const running = Boolean(project.activeJob)
  const ready = (mode === 'file' ? Boolean(file) : text.trim().split(/\s+/).length >= 20) && agreed && chosen?.available !== false
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold tracking-wide text-brand-700 uppercase"><Link to="/app/datalab" className="hover:underline">Data Lab · Qualitative</Link></p>
          <h1 className="text-2xl font-medium text-fg">{project.title}</h1>
          <p className="text-sm text-fg-muted">{project.purpose || 'No research question yet.'}</p>
        </div>
        <Button variant="ghost" size="sm" disabled={busy || running}
          onClick={() => { if (window.confirm('Delete this project, its transcripts and reports?')) void act(async () => { await data.datalab.remove(project.id); navigate('/app/datalab') }) }}>
          Delete
        </Button>
      </header>
      {error && <Alert tone="danger">{error}</Alert>}

      <Card className="space-y-4 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Transcripts</h2>
        {project.documents.length > 0 ? (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {project.documents.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1"><span className="font-medium text-fg">{d.label}</span> <span className="text-fg-muted">· {d.words.toLocaleString()} words{d.replaced ? ` · ${d.replaced} replaced` : ''}</span></span>
                <button className="rounded p-1 text-fg-subtle hover:text-red-600" aria-label={`Remove ${d.label}`} disabled={busy || running}
                  onClick={() => void act(() => data.datalab.removeDocument(project.id, d.id))}><Trash2 className="size-4" aria-hidden /></button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-fg-muted">Add each interview, focus group or set of open answers. PaperAid replaces the names you list, and any phone number, email or ID number, before anything is stored.</p>
        )}
        <div className="space-y-3 rounded-xl border border-line p-4">
          <div className="flex gap-2" role="tablist" aria-label="How to add a transcript">
            {(['file', 'paste'] as const).map((m) => (
              <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
                className={`rounded-full px-3 py-1 text-sm ring-1 ${mode === m ? 'bg-brand-700 text-white ring-brand-700' : 'text-fg-muted ring-line'}`}>
                {m === 'file' ? 'Upload a file' : 'Paste text'}
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input label="Name in the report" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder={`e.g. Interview ${project.documents.length + 1}`} />
            <Select label="Which country is it from?" value={country} onChange={(e) => setCountry(e.target.value)}>
              {countries.map((c) => <option key={c.iso3} value={c.iso3}>{c.name}</option>)}
            </Select>
          </div>
          {chosen && !chosen.available && (
            <Alert tone="warning">Data Lab isn't available yet for data from {chosen.iso3 === 'OTHER' ? 'this country' : chosen.name}: its data protection law sets rules we're making sure PaperAid meets first. Data from Uganda works as normal.</Alert>
          )}
          {mode === 'file' ? (
            <Input label="Transcript file" type="file" accept=".txt,.docx,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} hint="Text (.txt), Word (.docx) or a text PDF." />
          ) : (
            <TextArea label="Transcript" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          )}
          <TextArea label="Names to replace (optional)" rows={3} value={names} onChange={(e) => setNames(e.target.value)}
            hint="One per line, as Name = code, e.g. Agnes Akello = Participant A. Replaced before the transcript is stored or analysed." />
          <Checkbox checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
            label="My participants agreed to their words being analysed (with ethics approval where my study needs it), and I've listed the names to replace." />
          <Button loading={busy} disabled={!ready || running} onClick={() => void add()}>Add transcript</Button>
        </div>
      </Card>

      <Card className="space-y-4 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Analysis</h2>
        {running ? (
          <p className="flex items-center gap-2 text-sm font-medium text-fg" role="status"><Loader2 className="size-5 animate-spin text-brand-700" aria-hidden /> Finding the themes in your transcripts… this usually takes a few minutes.</p>
        ) : (
          <>
            {!project.qualPriced && <Alert tone="info">The qualitative analysis isn't available yet. You can add your transcripts now.</Alert>}
            {project.reportFailure && <Alert tone="warning">{project.reportFailure}</Alert>}
            <p className="text-sm text-fg-muted">
              PaperAid codes every transcript, groups the codes into themes that answer your question, and quotes participants exactly: every quote is checked word for word against its transcript.
              {words > 0 && ` ${project.documents.length} transcript${project.documents.length === 1 ? '' : 's'}, ${words.toLocaleString()} words.`}
            </p>
            <Button loading={busy} disabled={!project.qualPriced || project.documents.length === 0} onClick={() => void act(async () => { await data.datalab.startThemes(project.id); await load() })}>
              <Sparkles className="size-4" aria-hidden /> {project.reports.length ? 'Analyse again' : 'Find the themes'}
            </Button>
          </>
        )}
        {report && (
          <>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void act(() => data.datalab.downloadReport(project.id, `${name}.docx`))}><Download className="size-4" aria-hidden /> Download Word</Button>
              <Button variant="secondary" disabled={busy} onClick={() => void act(() => data.datalab.downloadReportPdf(project.id, `${name}.pdf`))}><Download className="size-4" aria-hidden /> PDF</Button>
              <Button variant="secondary" disabled={busy} onClick={() => void act(() => data.datalab.downloadCodebook(project.id, `${name} - codebook.xlsx`))}><FileSpreadsheet className="size-4" aria-hidden /> Codebook</Button>
            </div>
            <ReportView projectId={project.id} report={report} />
          </>
        )}
      </Card>
    </div>
  )
}
