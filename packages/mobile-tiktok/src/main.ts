import { connectHost } from "./host";
import type { Export } from "./archive";
import { loadExport } from "./archive";
import { runExtractionAsync } from "./extract";
import { Screens } from "./review/screens";
import { Controller } from "./controller";

const root = document.getElementById("app") as HTMLElement;
const host = connectHost(window, document, () => root.getBoundingClientRect().height);

let controller: Controller | null = null;

// One turn of the event loop, so the browser can paint between tables.
const yieldToUi = () => new Promise<void>((r) => window.setTimeout(r, 0));

host.ready.then((locale) => {
  const deps = {
    host,
    screens: null as unknown as Screens,
    loadExport,
    runExtraction: (exp: Export) => runExtractionAsync(exp, yieldToUi),
    sessionId: String(Date.now()),
    appVersion: __APP_VERSION__,
    userAgent: navigator.userAgent,
    now: () => new Date().toISOString(),
    yieldToUi,
  };
  controller = new Controller(deps);
  deps.screens = new Screens(root, locale, controller.handlers, () => host.resize());
  controller.start();
}).catch(() => {
  // A failure while wiring up or drawing the first screen would otherwise leave
  // the task sitting on a blank page with no exit.
  if (controller) controller.onUnhandled();
});

window.onerror = function () {
  // Never surface exception text. The controller maps failures to fixed
  // categories; anything reaching here is shown as the generic error.
  root.textContent = "";
  if (controller) controller.onUnhandled();
  return true;
};

window.onunhandledrejection = function () {
  // Same rule for a rejected promise nothing caught: the reason is never read,
  // so nothing from the archive can reach the host through this path.
  if (controller) controller.onUnhandled();
  return true;
};
