import { Weak } from '../../../../helpers'
import { ReactFactoryContext } from '../../factory'
import { PropsUIPromptConfirm } from '../../../../types/prompts'
import { Translator } from '../../../../translator'
import { BodyLarge } from '../elements/text'
import { PrimaryButton } from '../elements/button'
import { JSX } from 'react'
import React from 'react'

// The waiting state mirrors file_input.tsx in this package and is a framework-level
// fix kept for upstreaming (ADR-0002); upstream's Confirm has no busy state as of
// eyra/feldspar develop 2026-09-03. The busy state is keyed to the page's own
// `resolve`, so a Confirm rendered for the next page never inherits it.
type Props = Weak<PropsUIPromptConfirm> & ReactFactoryContext

export const Confirm = (props: Props): JSX.Element => {
  const { resolve } = props
  const { text, ok, cancel } = prepareCopy(props)
  const [busy, setBusy] = React.useState<{ resolve: typeof resolve, choice: 'ok' | 'cancel' } | null>(null)
  const waiting = busy !== null && busy.resolve === resolve

  function handleOk (): void {
    if (waiting) return
    setBusy({ resolve, choice: 'ok' })
    resolve?.({ __type__: 'PayloadTrue', value: true })
  }

  function handleCancel (): void {
    if (waiting) return
    setBusy({ resolve, choice: 'cancel' })
    resolve?.({ __type__: 'PayloadFalse', value: false })
  }

  return (
    <>
      <BodyLarge text={text} margin='mb-4' />
      <div className='flex flex-row gap-4'>
        <PrimaryButton label={ok} onClick={handleOk} color='text-grey1 bg-tertiary' spinning={waiting && busy?.choice === 'ok'} enabled={!waiting} />
        {cancel !== undefined && (
          <PrimaryButton label={cancel} onClick={handleCancel} color='text-white bg-primary' spinning={waiting && busy?.choice === 'cancel'} enabled={!waiting} />
        )}
      </div>
    </>
  )
}

interface Copy {
  text: string
  ok: string
  cancel: string | undefined
}

function prepareCopy ({ text, ok, cancel, locale }: Props): Copy {
  return {
    text: Translator.translate(text, locale),
    ok: Translator.translate(ok, locale),
    cancel: cancel !== undefined ? Translator.translate(cancel, locale) : undefined
  }
}
