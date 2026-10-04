import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { IdentifierRules } from '../../lib/datalab-types'
import { flagColumns, parseCsv } from './upload'

const backend = resolve(__dirname, '../../../../backend')
const rules = JSON.parse(readFileSync(resolve(backend, 'app/datalab/engine/identifiers.json'), 'utf-8')) as IdentifierRules

describe('columns that may identify people or places', () => {
  it('are flagged in the browser exactly as on the server (one shared rule file)', () => {
    const rows = parseCsv(readFileSync(resolve(backend, 'tests/fixtures/identifiers_fixture.csv'), 'utf-8'), ',')
    const expected = JSON.parse(readFileSync(resolve(backend, 'tests/fixtures/identifiers_expected.json'), 'utf-8')) as { flagged: string[] }
    expect(flagColumns(rows, rules).map((f) => f.name)).toEqual(expected.flagged)
  })

  it('reads quoted cells, doubled quotes and line breaks inside quotes', () => {
    expect(parseCsv('a;b\n"x;y";"he said ""hi"""\n"two\nlines";3\n', ';')).toEqual([['a', 'b'], ['x;y', 'he said "hi"'], ['two\nlines', '3']])
  })
})
