import { isPropsUIPromptNotice } from './types'

describe('isPropsUIPromptNotice', () => {
  it('accepts a notice body', () => {
    expect(isPropsUIPromptNotice({ __type__: 'PropsUIPromptNotice', text: 'x' })).toBe(true)
  })
  it('rejects other prompts and junk', () => {
    expect(isPropsUIPromptNotice({ __type__: 'PropsUIPromptConfirm', text: 'x', ok: 'y' })).toBe(false)
    expect(isPropsUIPromptNotice(null)).toBe(false)
    expect(isPropsUIPromptNotice('PropsUIPromptNotice')).toBe(false)
  })
})
