import { readDrop, hasFiles, DropItem } from './drop'

const f = (name: string): File => new File([new ArrayBuffer(4)], name)

const fileItem = (file: File, entry: { isDirectory: boolean, name: string } | null): DropItem => ({
  kind: 'file',
  getAsFile: () => file,
  webkitGetAsEntry: () => entry
})

describe('readDrop', () => {
  it('returns the files of a drop', () => {
    const a = f('a.zip')
    const b = f('b.zip')
    const result = readDrop({
      items: [
        fileItem(a, { isDirectory: false, name: 'a.zip' }),
        fileItem(b, { isDirectory: false, name: 'b.zip' })
      ],
      files: [a, b]
    })
    expect(result.files.map((x) => x.name)).toEqual(['a.zip', 'b.zip'])
    expect(result.folders).toEqual([])
  })

  it('reports a folder by name and does not return it as a file', () => {
    const a = f('a.zip')
    const folder = f('takeout')
    const result = readDrop({
      items: [
        fileItem(folder, { isDirectory: true, name: 'takeout' }),
        fileItem(a, { isDirectory: false, name: 'a.zip' })
      ],
      files: [folder, a]
    })
    expect(result.files.map((x) => x.name)).toEqual(['a.zip'])
    expect(result.folders).toEqual(['takeout'])
  })

  it('treats a null entry as a file', () => {
    const a = f('a.zip')
    const result = readDrop({ items: [fileItem(a, null)], files: [a] })
    expect(result.files).toEqual([a])
  })

  it('treats an item without webkitGetAsEntry as a file', () => {
    const a = f('a.zip')
    const result = readDrop({ items: [{ kind: 'file', getAsFile: () => a }], files: [a] })
    expect(result.files).toEqual([a])
  })

  it('skips items that are not files, such as dragged text', () => {
    const a = f('a.zip')
    const result = readDrop({
      items: [{ kind: 'string', getAsFile: () => null }, fileItem(a, null)],
      files: [a]
    })
    expect(result.files).toEqual([a])
  })

  it('falls back to the file list when there are no items', () => {
    const a = f('a.zip')
    expect(readDrop({ files: [a] }).files).toEqual([a])
    expect(readDrop({ items: [], files: [a] }).files).toEqual([a])
  })
})

describe('hasFiles', () => {
  it('is true only when the drag carries files', () => {
    expect(hasFiles({ types: ['Files'] })).toBe(true)
    expect(hasFiles({ types: ['text/plain'] })).toBe(false)
    expect(hasFiles(null)).toBe(false)
    expect(hasFiles(undefined)).toBe(false)
  })
})
