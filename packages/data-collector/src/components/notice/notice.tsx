import { BodyLarge, ReactFactoryContext } from "@eyra/feldspar"
import { JSX, useEffect } from "react"
import { resolveText } from "../../locale/text"
import { PropsUIPromptNotice } from "./types"

type Props = PropsUIPromptNotice & ReactFactoryContext

/**
 * Display-only prompt. Resolves its render promise on mount so the Python
 * generator advances without a participant action: the terminal
 * task-not-completed page must let the nonzero exit fire (ADR-0039) while
 * leaving the host's Close control as the only visible exit. A second
 * resolve (React StrictMode double-mount in dev) lands on a settled promise
 * and is a no-op.
 */
export const Notice = (props: Props): JSX.Element => {
  const { resolve, locale } = props
  const text = resolveText(props.text, locale)

  useEffect(() => {
    resolve?.({ __type__: 'PayloadVoid', value: undefined })
  }, [resolve])

  return <BodyLarge text={text} margin='mb-4' />
}
