import { PromptFactory, ReactFactoryContext } from "@eyra/feldspar"
import { Notice } from "./notice"
import { isPropsUIPromptNotice } from "./types"

export class NoticeFactory implements PromptFactory {
  create(body: unknown, context: ReactFactoryContext) {
    if (isPropsUIPromptNotice(body)) {
      return <Notice {...body} {...context} />;
    }
    return null;
  }
}
