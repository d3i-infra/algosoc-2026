import { serializeTable } from './serialize'
import { TableWithContext } from './types'

function makeTable (): TableWithContext {
  const body = { rows: [{ id: '0', cells: ['hello_world.txt', '12'] }] }
  return {
    __type__: 'PropsUITable',
    id: 't1',
    head: { cells: ['filename', 'size'] },
    body,
    title: 'Files',
    description: '',
    deletedRowCount: 2,
    annotations: [],
    originalBody: body,
    deletedRows: [],
    folded: false,
    deleteOption: true
  }
}

describe('serializeTable', () => {
  it('writes the validation record beside the deleted row count', () => {
    const validation = { category: 'json_en', basis: 'strong' }

    const result = serializeTable(makeTable(), validation)

    expect(Object.keys(result)).toEqual(['t1', 'deleted row count', 'validation'])
    expect(result.validation).toBe(validation)
    expect(result['deleted row count']).toBe('2')
    expect(result.t1).toEqual([{ filename: 'hello_world.txt', size: '12' }])
  })

  it('omits the validation key when no record is given', () => {
    const result = serializeTable(makeTable())

    expect(Object.keys(result)).toEqual(['t1', 'deleted row count'])
  })
})
