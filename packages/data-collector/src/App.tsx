import { DataSubmissionPageFactory, ScriptHostComponent } from "@eyra/feldspar";
import { ConsentFormVizFactory } from "./factories/consent_form_viz";
import { FileInputMultipleFactory } from "./components/file_input_multiple/factory"
import { ErrorPageFactory } from "./components/error_page/factory"
import { QuestionnaireFactory } from "./components/questionnaire/factory"
import { RetryPromptFactory } from "./components/retry_prompt/factory"
import { normalizeLocale, DEFAULT_UI_LOCALE } from "./locale/policy"

// DEV-gated query param: the Playwright e2e injection point. Production locale
// comes only from mono's live-init (LiveBridge), never from the URL.
const devLocale = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get('locale') ?? undefined
  : undefined

// Study preview builds (VITE_STANDALONE=true, the gh-pages preview) run on the
// fake bridge, so no host supplies a locale; this Dutch-language study shows
// them in Dutch. Dev and production are unaffected: dev keeps the ?locale=
// injection point above, production takes the host's locale.
const isPreviewBuild = import.meta.env.VITE_STANDALONE === "true"
const previewLocale = isPreviewBuild ? "nl" : undefined

function App() {
  return (
    <div className="App">
      <ScriptHostComponent
        workerUrl="./py_worker.js"
        standalone={import.meta.env.DEV || isPreviewBuild}
        logLevel={import.meta.env.DEV ? "debug" : "info"}
        platform={import.meta.env.VITE_PLATFORM}
        defaultLocale={DEFAULT_UI_LOCALE}
        locale={devLocale ?? previewLocale}
        mapLocale={normalizeLocale}
        factories={[
          new DataSubmissionPageFactory({
            promptFactories: [
                new ConsentFormVizFactory(),
                new FileInputMultipleFactory(),
                new ErrorPageFactory(),
                new QuestionnaireFactory(),
                new RetryPromptFactory(),
            ],
          }),
        ]}
      />
    </div>
  );
}

export default App;
