import { parseAccept, isAccepted, partitionAccepted } from './accept'

const f = (name: string, type = ''): File => new File([new ArrayBuffer(4)], name, { type })

describe('parseAccept', () => {
  it('maps a known MIME type to its extensions and aliases', () => {
    const rule = parseAccept('application/zip')
    expect(rule.open).toBe(false)
    expect([...rule.extensions]).toEqual(['.zip'])
    expect(rule.mimeTypes.has('application/zip')).toBe(true)
    expect(rule.mimeTypes.has('application/x-zip-compressed')).toBe(true)
  })

  it('reads a comma-separated list and ignores spacing and case', () => {
    const rule = parseAccept(' Application/JSON ,application/zip ')
    expect([...rule.extensions].sort()).toEqual(['.json', '.zip'])
  })

  it('reads a bare extension token', () => {
    const rule = parseAccept('.ZIP')
    expect(rule.open).toBe(false)
    expect(rule.extensions.has('.zip')).toBe(true)
  })

  it('is open when the string is empty', () => {
    expect(parseAccept('').open).toBe(true)
  })

  it('is open when any token cannot be interpreted', () => {
    expect(parseAccept('application/zip, application/x-unheard-of').open).toBe(true)
    expect(parseAccept('image/*').open).toBe(true)
  })

  it('is open, and does not throw, for a token that names an Object.prototype member', () => {
    expect(parseAccept('constructor').open).toBe(true)
    expect(parseAccept('toString').open).toBe(true)
    expect(parseAccept('__proto__').open).toBe(true)
    expect(parseAccept('application/zip, constructor').open).toBe(true)
  })
})

describe('isAccepted', () => {
  const zip = parseAccept('application/zip')

  it('accepts a zip by extension whatever its type', () => {
    expect(isAccepted(f('data.zip', 'application/zip'), zip)).toBe(true)
    expect(isAccepted(f('data.zip', 'application/octet-stream'), zip)).toBe(true)
  })

  it('accepts a Windows zip: alias type, or empty type', () => {
    expect(isAccepted(f('data.zip', 'application/x-zip-compressed'), zip)).toBe(true)
    expect(isAccepted(f('data.zip', ''), zip)).toBe(true)
  })

  it('ignores the case of the extension', () => {
    expect(isAccepted(f('EXPORT.ZIP'), zip)).toBe(true)
  })

  it('accepts by type when the extension is unfamiliar', () => {
    expect(isAccepted(f('export.archive', 'application/zip'), zip)).toBe(true)
  })

  it('accepts by alias type when the extension is unfamiliar', () => {
    expect(isAccepted(f('data.dat', 'application/x-zip-compressed'), zip)).toBe(true)
  })

  it('accepts an ambiguous file: no extension and no type', () => {
    expect(isAccepted(f('export'), zip)).toBe(true)
  })

  it('accepts a file without an extension whatever its type', () => {
    expect(isAccepted(f('export', 'application/pdf'), zip)).toBe(true)
  })

  it('treats a leading dot as a name, not an extension', () => {
    expect(isAccepted(f('.hidden'), zip)).toBe(true)
  })

  it('refuses a clear mismatch', () => {
    expect(isAccepted(f('notes.pdf', 'application/pdf'), zip)).toBe(false)
    expect(isAccepted(f('notes.pdf', ''), zip)).toBe(false)
    expect(isAccepted(f('export.zip.download', ''), zip)).toBe(false)
  })

  it('accepts everything under an open rule', () => {
    expect(isAccepted(f('notes.pdf', 'application/pdf'), parseAccept(''))).toBe(true)
  })
})

describe('partitionAccepted', () => {
  it('splits a batch, keeping order, and reports refused names', () => {
    const batch = [f('a.zip'), f('notes.pdf', 'application/pdf'), f('b.zip')]
    const { accepted, rejected } = partitionAccepted(batch, 'application/zip')
    expect(accepted.map((x) => x.name)).toEqual(['a.zip', 'b.zip'])
    expect(rejected).toEqual(['notes.pdf'])
  })

  it('accepts json when the prompt advertises it', () => {
    const { accepted, rejected } = partitionAccepted(
      [f('user_data.json', 'application/json')],
      'application/json, application/zip'
    )
    expect(accepted).toHaveLength(1)
    expect(rejected).toEqual([])
  })
})
