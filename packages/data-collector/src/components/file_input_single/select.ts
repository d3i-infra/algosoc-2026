// Pure selection logic for the single-file input. A drop can carry several
// files even though this prompt takes one: the first is kept and the rest
// are reported, so the component can say so instead of discarding silently.
// An empty batch (everything in it was refused) leaves the selection as is.
export function pickSingle (
  current: File | undefined,
  incoming: File[]
): { file: File | undefined, extra: string[] } {
  if (incoming.length === 0) return { file: current, extra: [] }
  return { file: incoming[0], extra: incoming.slice(1).map((f) => f.name) }
}
