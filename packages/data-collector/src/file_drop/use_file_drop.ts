import * as React from 'react'
import { DropResult, hasFiles, readDrop } from './drop'
import { installDropGuard } from './guard'

export interface ZoneProps {
  onDragEnter: (event: React.DragEvent<HTMLElement>) => void
  onDragOver: (event: React.DragEvent<HTMLElement>) => void
  onDragLeave: (event: React.DragEvent<HTMLElement>) => void
  onDrop: (event: React.DragEvent<HTMLElement>) => void
}

/**
 * Wires a drop zone. `enabled` is false once the participant has pressed
 * Continue: a drop is then still cancelled (so the browser does not open the
 * file) but no longer changes the selection. `active` is always false while
 * `enabled` is false.
 */
export function useFileDrop (
  onDrop: (drop: DropResult) => void,
  enabled: boolean
): { active: boolean, zoneProps: ZoneProps } {
  const [active, setActive] = React.useState<boolean>(false)
  // dragenter and dragleave fire for every child element the pointer crosses,
  // so the zone is "left" only when the count of enters returns to zero.
  const depth = React.useRef<number>(0)

  React.useEffect(() => installDropGuard(window), [])

  const zoneProps: ZoneProps = {
    onDragEnter: (event) => {
      if (!hasFiles(event.dataTransfer)) return
      event.preventDefault()
      depth.current += 1
      setActive(true)
    },
    onDragOver: (event) => {
      if (!hasFiles(event.dataTransfer)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = enabled ? 'copy' : 'none'
    },
    onDragLeave: () => {
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setActive(false)
    },
    onDrop: (event) => {
      event.preventDefault()
      depth.current = 0
      setActive(false)
      // readDrop must run inside the handler: the DataTransfer is emptied
      // once the event has been dispatched.
      if (enabled) onDrop(readDrop(event.dataTransfer))
    }
  }

  // A disabled zone is never shown as a drop target, whatever the pointer
  // is doing: the highlight must agree with the "not allowed" cursor.
  return { active: active && enabled, zoneProps }
}
