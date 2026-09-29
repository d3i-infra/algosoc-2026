// A file dropped anywhere except on a drop zone (beside it, or on a page that
// has none) gets the browser's default handling: it opens the file in place of
// the page, which ends the participant's session. This guard cancels that
// default for the task app's own document. It cannot reach the host page
// around the iframe: drag events do not cross documents. It is installed once,
// for the whole app, by `App`.
import { hasFiles } from './drop'

export interface GuardEvent {
  defaultPrevented: boolean
  dataTransfer: { types: readonly string[], dropEffect: string } | null
  preventDefault: () => void
}

export function guardHandler (event: GuardEvent): void {
  if (event.dataTransfer === null || !hasFiles(event.dataTransfer)) return
  // The drop zone's own handler runs first and cancels the event. When it has
  // not, the pointer is outside the zone: show the "not allowed" cursor.
  if (!event.defaultPrevented) event.dataTransfer.dropEffect = 'none'
  event.preventDefault()
}

export function installDropGuard (
  target: Pick<Window, 'addEventListener' | 'removeEventListener'>
): () => void {
  const listener = (event: Event): void => guardHandler(event as DragEvent)
  target.addEventListener('dragover', listener)
  target.addEventListener('drop', listener)
  return () => {
    target.removeEventListener('dragover', listener)
    target.removeEventListener('drop', listener)
  }
}
