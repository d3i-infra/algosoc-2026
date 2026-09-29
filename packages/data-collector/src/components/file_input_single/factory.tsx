import {
    PromptFactory,
    ReactFactoryContext
} from "@eyra/feldspar"
import { FileInputSingle } from "./file_input_single"
import { PropsUIPromptFileInputSingle } from "./types"

export class FileInputSingleFactory implements PromptFactory {
  create(body: unknown, context: ReactFactoryContext) {
    if (this.isBody(body)) {
      return <FileInputSingle {...body} {...context} />;
    }
    return null;
  }

  private isBody(body: unknown): body is PropsUIPromptFileInputSingle {
    return (
      (body as PropsUIPromptFileInputSingle).__type__ === "PropsUIPromptFileInputSingle"
    );
  }
}
