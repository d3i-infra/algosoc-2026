// Applies a prompt's `accept` string to files that did not come through the
// file picker. The browser enforces `accept` in the picker only; a drop
// ignores it. The check is deliberately lenient: refusing a valid export
// blocks a donation outright, while letting a wrong file through only costs
// the participant the existing retry prompt. Python stays the authority on
// what is rejected (the size guard, then zip and DDP validation); this is a courtesy, not a safety boundary.

interface Known {
  extensions: string[]
  aliases: string[]
}

// The MIME type reported for a zip differs per operating system (Windows
// reports application/x-zip-compressed) and is sometimes empty, so each
// known type carries its aliases and its extensions.
const KNOWN: Record<string, Known> = {
  'application/zip': {
    extensions: ['.zip'],
    aliases: ['application/x-zip-compressed', 'application/x-zip']
  },
  'application/json': { extensions: ['.json'], aliases: [] },
  'text/plain': { extensions: ['.txt'], aliases: [] },
  'text/csv': { extensions: ['.csv'], aliases: [] }
}

export interface AcceptRule {
  extensions: Set<string>
  mimeTypes: Set<string>
  // True when the accept string is empty or holds a token this module cannot
  // interpret. An open rule accepts every file.
  open: boolean
}

export function parseAccept (accept: string): AcceptRule {
  const rule: AcceptRule = { extensions: new Set(), mimeTypes: new Set(), open: false }
  const tokens = accept.split(',').map((t) => t.trim().toLowerCase()).filter((t) => t !== '')
  if (tokens.length === 0) rule.open = true
  for (const token of tokens) {
    if (token.startsWith('.')) {
      rule.extensions.add(token)
      continue
    }
    // Own properties only: `in` would also match names inherited from
    // Object.prototype, such as "constructor".
    if (!Object.prototype.hasOwnProperty.call(KNOWN, token)) {
      rule.open = true
      continue
    }
    const known = KNOWN[token]
    rule.mimeTypes.add(token)
    known.aliases.forEach((alias) => rule.mimeTypes.add(alias))
    known.extensions.forEach((extension) => rule.extensions.add(extension))
  }
  return rule
}

function extensionOf (name: string): string {
  const dot = name.lastIndexOf('.')
  // A dot at the start (".hidden") or at the end ("archive.") leaves nothing
  // to judge by, so the name counts as having no extension.
  if (dot <= 0 || dot === name.length - 1) return ''
  return name.slice(dot).toLowerCase()
}

export function isAccepted (file: { name: string, type: string }, rule: AcceptRule): boolean {
  if (rule.open) return true
  const extension = extensionOf(file.name)
  const type = file.type.toLowerCase()
  if (extension !== '' && rule.extensions.has(extension)) return true
  if (type !== '' && rule.mimeTypes.has(type)) return true
  // No extension to judge by: let Python decide. A file is refused only when
  // it has an extension and neither that nor its type is allowed.
  return extension === ''
}

export function partitionAccepted (
  files: File[],
  accept: string
): { accepted: File[], rejected: string[] } {
  const rule = parseAccept(accept)
  const accepted: File[] = []
  const rejected: string[] = []
  for (const file of files) {
    if (isAccepted(file, rule)) accepted.push(file)
    else rejected.push(file.name)
  }
  return { accepted, rejected }
}
