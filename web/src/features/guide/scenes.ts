/* In-app guidance (owner, 2026-11-17, adopted from PaperAid Pro): what each section is for and how to use it, shown as
   a guide panel on the section, in the Help centre and in the optional welcome tour. Every statement must stay true
   to what PaperAid does today: change the guide when the section changes. Scenes are simplified sketches of the page,
   with the example topic used across PaperAid's own pages; they show what a person does, never invented results. */

export type GuideKey = 'dashboard' | 'coursework' | 'research-concept' | 'proposal' | 'funding-concept' | 'funding-proposal' | 'paper-check' | 'formatting'

export interface GuideStep {
  /** A few words: what to do. */
  title: string
  /** One or two sentences: how. */
  detail: string
  /** A link that takes the person straight to doing it. */
  action?: { label: string; to: string }
}

export interface Guide {
  title: string
  /** One sentence: what this section is for. */
  summary: string
  steps: GuideStep[]
  tips: string[]
}

export type DemoKind = 'input' | 'button' | 'accent' | 'card' | 'check' | 'chip' | 'note' | 'label'

export interface DemoElement {
  id: string
  kind: DemoKind
  area: 'bar' | 'main' | 'side'
  text: string
  sub?: string
  /** Hidden until a frame reveals it. */
  hidden?: boolean
  /** Takes the remaining width of the top bar. */
  grow?: boolean
}

export interface DemoFrame {
  /** The guide step this frame illustrates (highlighted beside the animation). */
  step: number
  to?: string
  type?: string
  click?: boolean
  reveal?: string[]
  hide?: string[]
  set?: Record<string, string>
  select?: string[]
}

export interface DemoScene {
  title: string
  elements: DemoElement[]
  frames: DemoFrame[]
}

const QUESTION = 'Critically evaluate the effectiveness of community health workers in improving maternal health'
const TOPIC = 'Malaria vaccine uptake among caregivers in Mukono District'

export const GUIDES: Record<GuideKey, Guide> = {
  dashboard: {
    title: 'Home',
    summary: 'Where you start anything new and pick up what PaperAid is writing for you.',
    steps: [
      { title: 'Start something new', detail: 'Choose coursework, a research concept note or proposal, or a funding concept note or proposal. A few questions, then PaperAid gets to work.' },
      { title: 'Continue writing', detail: 'Your two latest pieces of work are here with where each one stands. See all lists the rest.', action: { label: 'Your work', to: '/app/work' } },
      { title: 'Your work at a glance', detail: 'How many pieces are being written, need you or are ready, with each section’s own list.' },
      { title: 'Your own paper', detail: 'Redraft or format a paper you wrote yourself.', action: { label: 'Paper Check', to: '/app/new?service=PAPER_CHECK' } },
    ],
    tips: ['The left panel takes you to every section from any page.', 'Night mode is under Appearance at the bottom of the left panel.', 'Help, at the bottom of the left panel, explains every section.'],
  },
  coursework: {
    title: 'Coursework',
    summary: 'Essays, reports, case studies and reflective work, written to your question and brief from confirmed sources.',
    steps: [
      { title: 'Type your question', detail: 'Choose the type, then type the question exactly as your lecturer wrote it.', action: { label: 'Start coursework', to: '/app/start/coursework' } },
      { title: 'Add your brief', detail: 'Paste the question paper or marking guide if you have one. PaperAid reads the word limit and requirements from it.' },
      { title: 'Confirm the details', detail: 'Check your level and word limit. PaperAid then plans, researches, writes and checks every part of the question.' },
      { title: 'Review and download', detail: 'Read it on screen, ask for changes in your own words, then download Word or PDF.' },
    ],
    tips: ['A request such as “solve this for me” is not a question: type the question itself.', 'Every reference is a source PaperAid found and confirmed.'],
  },
  'research-concept': {
    title: 'Research concept note',
    summary: 'A short concept note for your research topic, from confirmed sources, that you can continue into the full proposal.',
    steps: [
      { title: 'Give your topic', detail: 'A working title or topic is enough to start; add your level and programme if you have them.', action: { label: 'Start a concept note', to: '/app/start/concept-paper' } },
      { title: 'Add your details', detail: 'Only your name is required. What you leave blank, PaperAid proposes and shows as proposed until you confirm it.' },
      { title: 'PaperAid writes it', detail: 'It researches confirmed sources and writes the concept note to the standard guide or your institution’s.' },
      { title: 'Continue into the proposal', detail: 'When you are ready, the same project continues into Chapter One of the full proposal.' },
    ],
    tips: ['Ask for changes in your own words, for example from your supervisor’s comments.'],
  },
  proposal: {
    title: 'Research proposal',
    summary: 'Chapters One to Three, written to your institution’s guide from sources PaperAid confirmed.',
    steps: [
      { title: 'Describe your study', detail: 'Your working title and level, and if you have them your objectives, setting and study design.', action: { label: 'Start a proposal', to: '/app/start/proposal' } },
      { title: 'Add your details', detail: 'Only your name is required. What you leave blank, PaperAid proposes and shows as proposed until you confirm it.' },
      { title: 'Chapter One', detail: 'PaperAid writes Chapter One from confirmed sources, with a conceptual framework figure you can edit.' },
      { title: 'Chapters Two and Three', detail: 'Continue when you are ready, ask for changes from your supervisor’s comments, and download Word, PDF or LaTeX.' },
    ],
    tips: ['Sample sizes are calculated by code from your own figures, never by a model.'],
  },
  'funding-concept': {
    title: 'Funding concept note',
    summary: 'A concept note for a call or a funder, checked against what the call asks.',
    steps: [
      { title: 'Describe your idea', detail: 'A short project title, the problem and who it affects, and what you propose to do about it.', action: { label: 'Start a concept note', to: '/app/start/concept-note' } },
      { title: 'Add the call', detail: 'Upload or paste the call or the funder’s guidelines, with their template if they gave one.' },
      { title: 'Check what PaperAid found', detail: 'PaperAid reads the call and shows the limits and questions it found. Keep them or correct them.' },
      { title: 'Review and download', detail: 'Every limit and form box is checked. Ask for changes, then download.' },
    ],
    tips: ['Figures only you can give are marked for you to fill in, never invented.'],
  },
  'funding-proposal': {
    title: 'Funding proposal',
    summary: 'A full proposal written to the call, with its logframe, workplan and budget tables built from your figures.',
    steps: [
      { title: 'Describe your project', detail: 'A short project title, the problem and who it affects, and what you propose to do about it.', action: { label: 'Start a proposal', to: '/app/start/funding' } },
      { title: 'Add the call', detail: 'Upload or paste the call or the funder’s guidelines, with their template if they gave one.' },
      { title: 'Check what PaperAid found', detail: 'PaperAid reads the call and shows the limits, questions and figures it found. Keep them or correct them.' },
      { title: 'Fill in your figures', detail: 'Amounts only you can give are marked as gaps. Fill them in on the page, with no AI, and every budget sum is worked out for you.' },
    ],
    tips: ['The logframe, workplan and M&E table come from one results model, so they always agree.'],
  },
  'paper-check': {
    title: 'Paper Check',
    summary: 'Your own paper redrafted in your voice, its sources checked and its layout finished.',
    steps: [
      { title: 'Upload your paper', detail: 'Upload the Word file (.docx). PaperAid shows your paper on screen at once.' },
      { title: 'Choose a redraft', detail: 'Light, standard or deep. A deep redraft shows a free preview before you decide.' },
      { title: 'Review every change', detail: 'Keep or undo each change. Your citations, quotations and numbers are kept exactly as they are.' },
      { title: 'Finish', detail: 'Check your sources, format it, or ask for more changes in your own words, all on the same screen.' },
    ],
    tips: ['Nothing is rewritten only to change its style: every change says why it was made.'],
  },
  formatting: {
    title: 'Academic formatting',
    summary: 'Your finished paper laid out in APA, Harvard or your institution’s guide, with every word kept.',
    steps: [
      { title: 'Upload your paper', detail: 'Upload the Word file (.docx) of your finished paper.' },
      { title: 'Choose the layout', detail: 'APA, Harvard or your institution’s guide: headings, spacing, page numbers and references.' },
      { title: 'Download', detail: 'Download the formatted Word file, or LaTeX if you need it. Your text is not changed.' },
    ],
    tips: ['Add your institution’s logo to the title page if your guide asks for it.'],
  },
}

export const SCENES: Record<GuideKey, DemoScene> = {
  dashboard: {
    title: 'Home',
    elements: [
      { id: 'new', kind: 'accent', area: 'bar', text: '+ New' },
      { id: 'work', kind: 'button', area: 'bar', text: 'Your work' },
      { id: 'l1', kind: 'label', area: 'main', text: 'Start something new' },
      { id: 'cw', kind: 'card', area: 'main', text: '+ Coursework', sub: 'Essays, reports, case studies' },
      { id: 'l2', kind: 'label', area: 'main', text: 'Continue writing', hidden: true },
      { id: 'row', kind: 'card', area: 'main', text: QUESTION, sub: 'Coursework · Writing…', hidden: true },
      { id: 'l3', kind: 'label', area: 'side', text: 'Your work' },
      { id: 'counts', kind: 'note', area: 'side', text: '1 being written', hidden: true },
      { id: 'own', kind: 'button', area: 'side', text: 'Redraft my paper' },
    ],
    frames: [
      { step: 0, to: 'cw', click: true, select: ['cw'] },
      { step: 1, reveal: ['l2', 'row'] },
      { step: 2, to: 'counts', reveal: ['counts'] },
      { step: 3, to: 'own', click: true },
    ],
  },
  coursework: {
    title: 'Coursework · Start',
    elements: [
      { id: 'essay', kind: 'button', area: 'bar', text: 'Essay' },
      { id: 'report', kind: 'button', area: 'bar', text: 'Report' },
      { id: 'case', kind: 'button', area: 'bar', text: 'Case study' },
      { id: 'q', kind: 'input', area: 'main', text: 'Your question' },
      { id: 'brief', kind: 'note', area: 'main', text: 'Paste the question paper (optional)' },
      { id: 'limit', kind: 'chip', area: 'main', text: 'Word limit found: 2,000', hidden: true },
      { id: 'go', kind: 'accent', area: 'side', text: 'Continue' },
      { id: 'level', kind: 'button', area: 'side', text: 'Later undergraduate', hidden: true },
      { id: 'done', kind: 'chip', area: 'side', text: 'Ready · Word · PDF', hidden: true },
    ],
    frames: [
      { step: 0, to: 'essay', click: true, select: ['essay'] },
      { step: 0, to: 'q', type: QUESTION },
      { step: 1, to: 'brief', click: true, set: { brief: 'Question paper pasted ✓' }, reveal: ['limit'] },
      { step: 2, to: 'go', click: true, reveal: ['level'] },
      { step: 3, to: 'done', reveal: ['done'], select: ['essay', 'done'] },
    ],
  },
  'research-concept': {
    title: 'Research concept note · Start',
    elements: [
      { id: 'topic', kind: 'input', area: 'bar', text: 'Working title or topic', grow: true },
      { id: 'name', kind: 'input', area: 'main', text: 'Your name' },
      { id: 'setting', kind: 'note', area: 'main', text: 'Where will the study take place? (optional)' },
      { id: 'proposed', kind: 'chip', area: 'main', text: 'Proposed by PaperAid · confirm later', hidden: true },
      { id: 'go', kind: 'accent', area: 'side', text: 'Write my concept note' },
      { id: 'written', kind: 'chip', area: 'side', text: 'Concept note written', hidden: true },
      { id: 'next', kind: 'button', area: 'side', text: 'Continue to Chapter One', hidden: true },
    ],
    frames: [
      { step: 0, to: 'topic', type: TOPIC },
      { step: 1, to: 'name', type: 'Grace Namukasa' },
      { step: 1, to: 'setting', reveal: ['proposed'] },
      { step: 2, to: 'go', click: true, reveal: ['written'], select: ['written'] },
      { step: 3, to: 'next', reveal: ['next'] },
    ],
  },
  proposal: {
    title: 'Research proposal',
    elements: [
      { id: 'topic', kind: 'input', area: 'bar', text: 'Working title or topic', grow: true },
      { id: 'design', kind: 'button', area: 'main', text: 'Study design' },
      { id: 'ch1', kind: 'card', area: 'main', text: '1.1 Background to the study', sub: 'Chapter One · from confirmed sources', hidden: true },
      { id: 'fig', kind: 'note', area: 'main', text: 'Conceptual framework figure', hidden: true },
      { id: 'go', kind: 'accent', area: 'side', text: 'Write Chapter One' },
      { id: 'ch2', kind: 'button', area: 'side', text: 'Continue to Chapter Two', hidden: true },
      { id: 'dl', kind: 'chip', area: 'side', text: 'Word · PDF · LaTeX', hidden: true },
    ],
    frames: [
      { step: 0, to: 'topic', type: TOPIC },
      { step: 1, to: 'design', click: true, set: { design: 'Quantitative' }, select: ['design'] },
      { step: 2, to: 'go', click: true, reveal: ['ch1', 'fig'] },
      { step: 3, to: 'ch2', reveal: ['ch2'], click: true },
      { step: 3, to: 'dl', reveal: ['dl'] },
    ],
  },
  'funding-concept': {
    title: 'Funding concept note · Start',
    elements: [
      { id: 'title', kind: 'input', area: 'bar', text: 'Project title', grow: true },
      { id: 'problem', kind: 'input', area: 'main', text: 'The problem, and who it affects' },
      { id: 'idea', kind: 'input', area: 'main', text: 'What you propose to do about it' },
      { id: 'call', kind: 'note', area: 'main', text: 'Upload or paste the call' },
      { id: 'found', kind: 'check', area: 'side', text: 'Limits found in the call', hidden: true },
      { id: 'qs', kind: 'check', area: 'side', text: 'Questions it asks', hidden: true },
      { id: 'go', kind: 'accent', area: 'side', text: 'Write my concept note' },
    ],
    frames: [
      { step: 0, to: 'title', type: 'Safer deliveries in Kamuli' },
      { step: 0, to: 'problem', type: 'Mothers reach care late in rural Kamuli' },
      { step: 0, to: 'idea', type: 'Train village health teams to refer mothers early' },
      { step: 1, to: 'call', click: true, set: { call: 'Call pasted ✓' } },
      { step: 2, reveal: ['found', 'qs'], select: ['found', 'qs'] },
      { step: 3, to: 'go', click: true },
    ],
  },
  'funding-proposal': {
    title: 'Funding proposal',
    elements: [
      { id: 'title', kind: 'input', area: 'bar', text: 'Project title', grow: true },
      { id: 'problem', kind: 'input', area: 'main', text: 'The problem, and who it affects' },
      { id: 'call', kind: 'note', area: 'main', text: 'Upload or paste the call' },
      { id: 'tables', kind: 'card', area: 'main', text: 'Logframe · Workplan · Budget', sub: 'Built from one results model', hidden: true },
      { id: 'gap', kind: 'note', area: 'side', text: 'Amount to be added by you', hidden: true },
      { id: 'saved', kind: 'chip', area: 'side', text: 'Budget totals worked out', hidden: true },
      { id: 'go', kind: 'accent', area: 'side', text: 'Write my proposal' },
    ],
    frames: [
      { step: 0, to: 'title', type: 'Safer deliveries in Kamuli' },
      { step: 0, to: 'problem', type: 'Mothers reach care late in rural Kamuli' },
      { step: 1, to: 'call', click: true, set: { call: 'Call pasted ✓' } },
      { step: 2, to: 'go', click: true, reveal: ['tables', 'gap'] },
      { step: 3, to: 'gap', click: true, set: { gap: 'Your figure added ✓' }, reveal: ['saved'], select: ['gap', 'saved'] },
    ],
  },
  'paper-check': {
    title: 'Paper Check',
    elements: [
      { id: 'upload', kind: 'note', area: 'bar', text: 'Upload your Word file (.docx)' },
      { id: 'para', kind: 'card', area: 'main', text: 'Community health workers have contributed to improved antenatal attendance…', sub: 'Your paper, as you wrote it' },
      { id: 'change', kind: 'card', area: 'main', text: 'Community health workers have improved antenatal attendance…', sub: 'Changed · why: clearer and shorter', hidden: true },
      { id: 'mode', kind: 'button', area: 'side', text: 'Standard redraft' },
      { id: 'go', kind: 'accent', area: 'side', text: 'Redraft my paper' },
      { id: 'keep', kind: 'button', area: 'side', text: 'Keep', hidden: true },
      { id: 'next', kind: 'chip', area: 'side', text: 'Check sources · Format', hidden: true },
    ],
    frames: [
      { step: 0, to: 'upload', click: true, set: { upload: 'my-paper.docx ✓' } },
      { step: 1, to: 'mode', click: true, select: ['mode'] },
      { step: 1, to: 'go', click: true, reveal: ['change', 'keep'] },
      { step: 2, to: 'keep', click: true, set: { keep: 'Kept ✓' }, select: ['mode', 'change'] },
      { step: 3, to: 'next', reveal: ['next'] },
    ],
  },
  formatting: {
    title: 'Academic formatting',
    elements: [
      { id: 'upload', kind: 'note', area: 'bar', text: 'Upload your Word file (.docx)' },
      { id: 'apa', kind: 'button', area: 'main', text: 'APA 7' },
      { id: 'harvard', kind: 'button', area: 'main', text: 'Harvard' },
      { id: 'guide', kind: 'button', area: 'main', text: 'My institution’s guide' },
      { id: 'go', kind: 'accent', area: 'side', text: 'Format my paper' },
      { id: 'dl', kind: 'chip', area: 'side', text: 'Formatted · Word', hidden: true },
    ],
    frames: [
      { step: 0, to: 'upload', click: true, set: { upload: 'my-paper.docx ✓' } },
      { step: 1, to: 'apa', click: true, select: ['apa'] },
      { step: 2, to: 'go', click: true, reveal: ['dl'], select: ['apa', 'dl'] },
    ],
  },
}

/** One line per frame: what is happening and why it matters. */
export const NARRATION: Record<GuideKey, string[]> = {
  dashboard: [
    'Choose what you need under Start something new.',
    'What PaperAid is writing appears under Continue writing.',
    'Your work shows where everything stands.',
    'Your own paper can be redrafted or formatted too.',
  ],
  coursework: [
    'Choose the kind of coursework.',
    'Type the question exactly as it was set.',
    'Paste your brief: PaperAid reads its limits.',
    'Confirm your level, and PaperAid gets to work.',
    'Read it on screen, then download Word or PDF.',
  ],
  'research-concept': [
    'A working title or topic is enough to start.',
    'Only your name is required.',
    'What you leave blank is proposed for you to confirm.',
    'PaperAid writes the concept note from confirmed sources.',
    'Continue it into the full proposal when you are ready.',
  ],
  proposal: [
    'Start from your working title or topic.',
    'Add what you know about the study, such as its design.',
    'Chapter One comes with its framework figure.',
    'Continue chapter by chapter when you are ready.',
    'Download Word, PDF or LaTeX.',
  ],
  'funding-concept': [
    'Give your project a short title.',
    'Say what the problem is and who it affects.',
    'Say what you propose to do, in your own words.',
    'Add the call or the funder’s guidelines.',
    'PaperAid shows what the call asks for.',
    'Then it writes the concept note to the call.',
  ],
  'funding-proposal': [
    'Give your project a short title.',
    'Say what the problem is and who it affects.',
    'Add the call: PaperAid reads what it requires.',
    'The tables are built from one results model.',
    'Fill in your own figures; the sums are worked out.',
  ],
  'paper-check': [
    'Upload your paper as a Word file.',
    'Choose how much to redraft.',
    'Each change shows what changed and why.',
    'Keep or undo every change.',
    'Then check your sources or format it.',
  ],
  formatting: [
    'Upload your finished paper.',
    'Choose the style your work needs.',
    'Download it laid out, with every word kept.',
  ],
}
