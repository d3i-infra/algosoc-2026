// Reads a drop event's DataTransfer into files and folder names. The shapes
// below are the slice of DataTransfer this module needs, so tests can pass
// plain objects and the component can pass the real thing.

export interface DropEntry {
  isDirectory: boolean
  name: string
}

export interface DropItem {
  kind: string
  getAsFile: () => File | null
  // Absent on very old browsers, and returns null for a DataTransfer built in
  // script. Both mean: treat the item as a file.
  webkitGetAsEntry?: () => DropEntry | null
}

export interface DropSource {
  items?: ArrayLike<DropItem>
  files: ArrayLike<File>
}

export interface DropResult {
  files: File[]
  folders: string[]
}

export function hasFiles (transfer: { types: readonly string[] } | null | undefined): boolean {
  return transfer != null && Array.from(transfer.types).includes('Files')
}

export function readDrop (source: DropSource): DropResult {
  const items = source.items === undefined ? [] : Array.from(source.items)
  if (items.length === 0) return { files: Array.from(source.files), folders: [] }

  const files: File[] = []
  const folders: string[] = []
  for (const item of items) {
    if (item.kind !== 'file') continue
    const entry = item.webkitGetAsEntry?.() ?? null
    if (entry !== null && entry.isDirectory) {
      folders.push(entry.name)
      continue
    }
    const file = item.getAsFile()
    if (file !== null) files.push(file)
  }
  return { files, folders }
}
