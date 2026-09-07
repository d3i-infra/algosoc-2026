export type Locale = "en" | "nl";
export type DonateResult =
  | { ok: true; status: number }
  | { ok: false; status: number; error: string };
export type Milestone =
  | "file_selected" | "archive_read" | "extracted" | "review_shown"
  | "consent_accepted" | "consent_declined" | "donate_started"
  | "donate_succeeded" | "donate_failed" | "error_shown"
  | "error_report_sent" | "error_report_skipped" | "exited";

export interface Host {
  ready: Promise<Locale>;
  donate(key: string, jsonString: string): Promise<DonateResult>;
  exit(code: number, info: string): void;
  log(milestone: Milestone): void;
  resize(): void;
}

interface PortLike {
  postMessage(message: unknown): void;
  onmessage: null | ((e: { data: unknown }) => void);
}

function toLocale(raw: unknown): Locale {
  const s = typeof raw === "string" ? raw.toLowerCase() : "";
  return s.indexOf("nl") === 0 ? "nl" : "en";
}

export function connectHost(win: Window, doc: Document, measure?: () => number): Host {
  let port: PortLike | null = null;
  const pending: { [key: string]: (r: DonateResult) => void } = {};
  let resolveReady: (l: Locale) => void = () => undefined;
  const ready = new Promise<Locale>((resolve) => { resolveReady = resolve; });

  function onPortMessage(e: { data: unknown }): void {
    const data = e.data as { __type__?: string; key?: string; status?: number; error?: string } | null;
    if (!data || typeof data.key !== "string") return;
    const settle = pending[data.key];
    if (!settle) return;
    if (data.__type__ === "DonateSuccess") {
      delete pending[data.key];
      settle({ ok: true, status: typeof data.status === "number" ? data.status : 0 });
    } else if (data.__type__ === "DonateError") {
      delete pending[data.key];
      settle({ ok: false, status: typeof data.status === "number" ? data.status : 0, error: typeof data.error === "string" ? data.error : "" });
    }
  }

  // A replaced channel can never answer the donations that were posted on it,
  // so settle them as a delivery failure: the controller shows the Failed
  // screen with Retry instead of waiting forever.
  function failPending(): void {
    const keys = Object.keys(pending);
    for (let i = 0; i < keys.length; i++) {
      const settle = pending[keys[i]];
      delete pending[keys[i]];
      settle({ ok: false, status: 0, error: "" });
    }
  }

  win.addEventListener("message", (event: MessageEvent) => {
    const data = event.data as { action?: string; locale?: unknown } | null;
    if (!data || data.action !== "live-init" || !event.ports || !event.ports[0]) return;
    // The host always builds a fresh MessageChannel when `app-loaded` arrives
    // and posts a second `live-init` with the new port2; only its iframe
    // `onload` path is guarded. Keeping the first port would leave every later
    // donate on a channel the host no longer listens on, so adopt the new port
    // the way feldspar's LiveBridge.updatePort does.
    const replaced = port !== null;
    port = event.ports[0] as unknown as PortLike;
    port.onmessage = onPortMessage;
    port.postMessage({ __type__: "CommandSystemEvent", name: "initialized" });
    if (replaced) failPending();
    resolveReady(toLocale(data.locale)); // idempotent: the first locale wins
  });

  win.parent.postMessage({ action: "app-loaded" }, "*");

  return {
    ready,
    donate(key, jsonString) {
      return new Promise<DonateResult>((resolve) => {
        if (!port) { resolve({ ok: false, status: 0, error: "no host" }); return; }
        pending[key] = resolve;
        port.postMessage({ __type__: "CommandSystemDonate", key, json_string: jsonString });
      });
    },
    exit(code, info) {
      if (port) port.postMessage({ __type__: "CommandSystemExit", code, info });
    },
    log(milestone) {
      if (port) port.postMessage({ __type__: "CommandSystemLog", json_string: JSON.stringify({ level: "info", message: milestone }) });
    },
    resize() {
      // Inside the iframe the body is never shorter than the frame's own
      // viewport, so once the host has grown the frame the old measurement
      // can only report the tall value back. A caller that can measure its
      // own content (the app root) passes that instead.
      const height = measure ? Math.ceil(measure()) : doc.body.scrollHeight;
      win.parent.postMessage({ action: "resize", height: height + 48 }, "*");
    },
  };
}
