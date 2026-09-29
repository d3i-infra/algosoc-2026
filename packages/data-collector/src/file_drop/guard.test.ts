import { guardHandler, GuardEvent } from './guard'

function event (types: string[], alreadyHandled: boolean): GuardEvent & { prevented: number } {
  const e = {
    prevented: 0,
    defaultPrevented: alreadyHandled,
    dataTransfer: { types, dropEffect: alreadyHandled ? 'copy' : 'none' },
    preventDefault () { this.prevented += 1 }
  }
  return e
}

describe('guardHandler', () => {
  it('stops the browser opening a file dropped beside the zone', () => {
    const e = event(['Files'], false)
    e.dataTransfer!.dropEffect = 'copy'
    guardHandler(e)
    expect(e.prevented).toBe(1)
    expect(e.dataTransfer!.dropEffect).toBe('none')
  })

  it('leaves the drop effect alone when the zone already handled the event', () => {
    const e = event(['Files'], true)
    guardHandler(e)
    expect(e.prevented).toBe(1)
    expect(e.dataTransfer!.dropEffect).toBe('copy')
  })

  it('ignores drags that carry no files', () => {
    const e = event(['text/plain'], false)
    guardHandler(e)
    expect(e.prevented).toBe(0)
  })

  it('ignores an event without a data transfer', () => {
    let prevented = 0
    guardHandler({ defaultPrevented: false, dataTransfer: null, preventDefault: () => { prevented += 1 } })
    expect(prevented).toBe(0)
  })
})
