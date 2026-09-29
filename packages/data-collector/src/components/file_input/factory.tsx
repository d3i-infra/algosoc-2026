import * as React from 'react'
import {
  FileInput,
  PromptFactory,
  ReactFactoryContext
} from "@eyra/feldspar"
import { LoadingNotice } from "../loading_notice/loading_notice"

type Props = React.ComponentProps<typeof FileInput>

// Wraps feldspar's own single-file prompt rather than forking it (ADR-0002):
// intercepting `resolve` tells us the file was submitted, so the loading
// notice can appear below the prompt while Python processes the archive.
const FileInputWithNotice = (props: Props): React.JSX.Element => {
  const [submitted, setSubmitted] = React.useState<boolean>(false)
  const { resolve } = props

  const handleResolve: Props['resolve'] = (payload) => {
    setSubmitted(true)
    resolve?.(payload)
  }

  return (
    <>
      <FileInput {...props} resolve={handleResolve} />
      {submitted && (
        <>
          <div className='mt-4' />
          <LoadingNotice locale={props.locale} />
        </>
      )}
    </>
  )
}

export class FileInputFactory implements PromptFactory {
  create(body: unknown, context: ReactFactoryContext) {
    if (this.isBody(body)) {
      return <FileInputWithNotice {...(body as Props)} {...context} />;
    }
    return null;
  }

  private isBody(body: unknown): boolean {
    return (
      (body as { __type__?: unknown }).__type__ === "PropsUIPromptFileInput"
    );
  }
}
