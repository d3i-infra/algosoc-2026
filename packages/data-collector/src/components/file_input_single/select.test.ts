import { pickSingle } from './select'

const f = (name: string): File => new File([new ArrayBuffer(4)], name)

describe('pickSingle', () => {
  it('takes the one incoming file', () => {
    const a = f('a.zip')
    expect(pickSingle(undefined, [a])).toEqual({ file: a, extra: [] })
  })

  it('replaces the current file', () => {
    const a = f('a.zip')
    const b = f('b.zip')
    expect(pickSingle(a, [b])).toEqual({ file: b, extra: [] })
  })

  it('keeps the first of several and names the rest', () => {
    const a = f('a.zip')
    const b = f('b.zip')
    const c = f('c.zip')
    expect(pickSingle(undefined, [a, b, c])).toEqual({ file: a, extra: ['b.zip', 'c.zip'] })
  })

  it('keeps the current file when nothing usable came in', () => {
    const a = f('a.zip')
    expect(pickSingle(a, [])).toEqual({ file: a, extra: [] })
    expect(pickSingle(undefined, [])).toEqual({ file: undefined, extra: [] })
  })
})
