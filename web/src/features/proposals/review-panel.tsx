import { Badge, Card } from '../../components/ui/primitives'
import type { ProposalReview } from '../../lib/proposal-types'
import { LEVELS, ReadinessList } from './shared'

const CHAPTERS = [
  [0, 'Whole proposal'],
  [1, 'Chapter One: General Introduction'],
  [2, 'Chapter Two: Literature Review'],
  [3, 'Chapter Three: Methodology'],
] as const
const KIND = { ALIGNMENT: 'Alignment', EVIDENCE: 'Evidence', METHOD: 'Method', STRUCTURE: 'Structure', TENSE: 'Tense', WRITING: 'Writing' } as const

/** An uploaded proposal checked against the UCU manual. Nothing in the proposal was changed. */
export function ProposalReviewPanel({ review }: { review: ProposalReview }) {
  return (
    <div className="space-y-6">
      <p className="text-sm text-fg-muted">
        Checked as a {LEVELS[review.level]} proposal against the UCU Academic Research Manual (2018), {review.words.toLocaleString()} words of main text. Faculties may set their
        own variations; check anything marked for review with your supervisor.
      </p>
      {CHAPTERS.map(([n, title]) => {
        const items = review.items.filter((i) => i.chapter === n)
        if (!items.length) return null
        return (
          <section key={n}>
            <h3 className="mb-2 text-base font-semibold">{title}</h3>
            <ReadinessList items={items} />
          </section>
        )
      })}
      {review.findings.length > 0 && (
        <section>
          <h3 className="mb-2 text-base font-semibold">What a supervisor is likely to raise</h3>
          <ul className="space-y-3">
            {review.findings.map((f, i) => (
              <li key={i}>
                <Card className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={f.severity === 'major' ? 'danger' : f.severity === 'moderate' ? 'warning' : 'neutral'}>{f.severity}</Badge>
                    <span className="text-xs font-semibold text-fg-subtle uppercase">{KIND[f.kind]}</span>
                  </div>
                  <p className="mt-2 text-sm font-medium">{f.issue}</p>
                  <p className="mt-1 text-sm text-fg-muted">{f.suggestion}</p>
                  {f.where && <p className="mt-1 text-xs text-fg-subtle">{f.where}</p>}
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
