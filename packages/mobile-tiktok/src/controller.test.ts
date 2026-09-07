import { Controller, ControllerDeps, EXIT } from "./controller";
import type { Host, DonateResult, Milestone } from "./host";
import type { Export } from "./archive";
import { ArchiveError } from "./archive";
import type { Extraction } from "./extract";
import type { ReviewState } from "./review/state";

type ScreenCall = { name: string; args: unknown[] };

function fakeScreens() {
  const calls: ScreenCall[] = [];
  const names = ["intro", "working", "retry", "tables", "confirm", "sending", "done", "failed", "error", "incomplete"];
  const raw: { [k: string]: (...a: unknown[]) => void } = {};
  for (const n of names) raw[n] = (...a: unknown[]) => calls.push({ name: n, args: a });
  return { screens: raw as unknown as ControllerDeps["screens"], raw, calls };
}

function fakeHost(results: DonateResult[]) {
  const donations: { key: string; json: string }[] = [];
  const logs: Milestone[] = [];
  const exits: [number, string][] = [];
  const host: Host = {
    ready: Promise.resolve("en"),
    donate: (key, json) => { donations.push({ key, json }); return Promise.resolve(results.shift() || { ok: true, status: 200 }); },
    exit: (code, info) => { exits.push([code, info]); },
    log: (m) => { logs.push(m); },
    resize: () => undefined,
  };
  return { host, donations, logs, exits };
}

const exportOk: Export = { kind: "json", data: {} };
const extractionOk: Extraction = { tables: [{ id: "tiktok_searches", columns: ["Date", "SearchTerm"], rows: [["2024", "q"]] }], errors: {} };

function make(overrides: Partial<ControllerDeps> = {}, results: DonateResult[] = []) {
  const s = fakeScreens();
  const h = fakeHost(results);
  const deps: ControllerDeps = {
    host: h.host,
    screens: s.screens,
    loadExport: () => Promise.resolve(exportOk),
    runExtraction: () => Promise.resolve(extractionOk),
    sessionId: "111",
    appVersion: "0.1.0",
    userAgent: "UA",
    now: () => "2026-09-06T00:00:00Z",
    yieldToUi: () => Promise.resolve(),
    ...overrides,
  };
  const c = new Controller(deps);
  c.start();
  return { c, s, h };
}

const tick = () => new Promise((r) => setTimeout(r, 0));
const file = new File(["x"], "a.zip");

test("happy path: file -> tables -> confirm -> donate -> done, exit 0", async () => {
  const { c, s, h } = make();
  expect(s.calls[0].name).toBe("intro");
  c.handlers.onFile(file);
  await tick(); await tick();
  expect(s.calls.map((x) => x.name)).toEqual(["intro", "working", "tables"]);
  c.handlers.onProceed();
  c.handlers.onDonate();
  await tick(); await tick();
  expect(h.donations[0].key).toBe("111-tiktok");
  expect(JSON.parse(h.donations[0].json)[0].tiktok_searches).toEqual([{ Date: "2024", SearchTerm: "q" }]);
  expect(h.exits).toEqual([[0, "completed"]]);
  expect(s.calls[s.calls.length - 1].name).toBe("done");
  expect(h.logs).toEqual(["file_selected", "archive_read", "extracted", "review_shown", "consent_accepted", "donate_started", "donate_succeeded", "exited"]);
});

test("decline records the literal and exits 0", async () => {
  const { c, h } = make();
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  c.handlers.onDecline(); await tick(); await tick();
  expect(h.donations[0].json).toBe('{"status": "data_submission declined"}');
  expect(h.exits).toEqual([[0, "completed"]]);
  expect(h.logs).toContain("consent_declined");
});

test("archive rejection shows retry; stop exits 4", async () => {
  const { c, s, h } = make({ loadExport: () => Promise.reject(new ArchiveError("not_tiktok")) });
  c.handlers.onFile(file); await tick(); await tick();
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "retry", args: ["not_tiktok"] });
  expect(h.logs).not.toContain("archive_read");
  c.handlers.onStop();
  expect(h.exits).toEqual([[4, "upload_rejected"]]);
  expect(s.calls[s.calls.length - 1].name).toBe("incomplete");
});

test("zero tables is extract_failed; report sends category only; exit 1", async () => {
  const { c, s, h } = make({ runExtraction: () => Promise.resolve({ tables: [], errors: {} }) });
  c.handlers.onFile(file); await tick(); await tick();
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "error", args: ["extract_failed"] });
  c.handlers.onReport(); await tick(); await tick();
  expect(h.donations[0].key).toBe("error-report");
  expect(JSON.parse(h.donations[0].json)).toEqual({ platform: "tiktok", category: "extract_failed", appVersion: "0.1.0", userAgent: "UA", timestamp: "2026-09-06T00:00:00Z" });
  expect(h.exits).toEqual([[1, "error"]]);
  expect(h.logs).toContain("error_report_sent");
});

test("skip report sends nothing and exits 1", async () => {
  const { c, s, h } = make({ runExtraction: () => { throw new Error("boom with data"); } });
  c.handlers.onFile(file); await tick(); await tick();
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "error", args: ["unexpected"] });
  c.handlers.onSkipReport();
  expect(h.donations).toEqual([]);
  expect(h.exits).toEqual([[1, "error"]]);
  expect(h.logs).toContain("error_report_skipped");
});

test("decline whose donation fails still completes silently", async () => {
  const { c, s, h } = make({}, [{ ok: false, status: 500, error: "x" }]);
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  c.handlers.onDecline(); await tick(); await tick();
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "done", args: [true] });
  expect(h.exits).toEqual([[0, "completed"]]);
  expect(h.logs).toContain("donate_failed");
  expect(h.logs).toContain("exited");
});

test("donation failure shows failed; retry resends same key; stop exits 3", async () => {
  const { c, s, h } = make({}, [{ ok: false, status: 500, error: "x" }, { ok: false, status: 0, error: "y" }]);
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  c.handlers.onDonate(); await tick(); await tick();
  expect(s.calls[s.calls.length - 1].name).toBe("failed");
  c.handlers.onRetryDonate(); await tick(); await tick();
  expect(h.donations.length).toBe(2);
  expect(h.donations[1].key).toBe("111-tiktok");
  c.handlers.onStop();
  expect(h.exits).toEqual([[3, "donation_failed"]]);
});

test("tables handlers delegate to state and re-render", async () => {
  const { c, s } = make();
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onQuery(0, "q");
  c.handlers.onDeleteMatches(0);
  c.handlers.onUndo();
  c.handlers.onSelectTable(0);
  expect(s.calls.filter((x) => x.name === "tables").length).toBe(5);
  c.handlers.onProceed();
  c.handlers.onBack();
  expect(s.calls[s.calls.length - 1].name).toBe("tables");
});

test("restart from the tables screen clears state and payload; onProceed and onRetryDonate are no-ops until a fresh file", async () => {
  const { c, s, h } = make();
  c.handlers.onFile(file); await tick(); await tick();
  expect(s.calls[s.calls.length - 1].name).toBe("tables");
  c.handlers.onRestart();
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "intro", args: [] });
  expect(h.logs).not.toContain("exited");

  // state is gone: onProceed reads it through withState, so with nothing
  // there it renders nothing and the last screen stays intro.
  const afterRestart = s.calls.length;
  c.handlers.onProceed();
  expect(s.calls.length).toBe(afterRestart);
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "intro", args: [] });

  // payload is gone too: send() bails before ever showing "sending".
  c.handlers.onRetryDonate();
  await tick(); await tick();
  expect(s.calls.some((x) => x.name === "sending")).toBe(false);
  expect(h.donations).toEqual([]);

  c.handlers.onFile(file); await tick(); await tick();
  expect(s.calls.slice(-2).map((x) => x.name)).toEqual(["working", "tables"]);
  expect(h.logs.filter((l) => l === "file_selected").length).toBe(2);
});

function datedExtraction(n: number): Extraction {
  const rows: string[][] = [];
  for (let i = 0; i < n; i++) {
    const month = 1 + Math.floor(i / 30);
    rows.push(["2024-0" + month + "-01 09:00:00", "https://x/v" + i]);
  }
  return { tables: [{ id: "tiktok_watch_history", columns: ["Date", "Link"], rows }], errors: {} };
}

test("selection, paging and month handlers delegate to state and re-render", async () => {
  const { c, s } = make({ runExtraction: () => Promise.resolve(datedExtraction(60)) });
  c.handlers.onFile(file); await tick(); await tick();
  const before = s.calls.filter((x) => x.name === "tables").length;
  const state = () => s.calls[s.calls.length - 1].args[0] as ReviewState;

  c.handlers.onToggleSelect(0, 1);
  expect(state().isSelected(0, 1)).toBe(true);
  expect(state().selectedCount(0)).toBe(1);

  c.handlers.onPage(0, 1);
  expect(state().tables[0].page).toBe(1);
  c.handlers.onPage(0, 99);
  expect(state().tables[0].page).toBe(1);

  c.handlers.onJumpToMonth(0, "2024-01");
  expect(state().tables[0].page).toBe(0);

  // No confirm dialog on this path: the participant ticked the rows.
  c.handlers.onDeleteSelected(0);
  expect(state().keptCount(0)).toBe(59);
  expect(state().selectedCount(0)).toBe(0);
  expect(state().visibleRows(0).indexOf(1)).toBe(-1);

  c.handlers.onUndo();
  expect(state().keptCount(0)).toBe(60);
  expect(s.calls.filter((x) => x.name === "tables").length).toBe(before + 6);
});

test("onSelectTable, onPage and onJumpToMonth tell the tables screen to scroll to top; other table actions do not", async () => {
  const { c, s } = make({ runExtraction: () => Promise.resolve(datedExtraction(60)) });
  c.handlers.onFile(file); await tick(); await tick();
  // Reads the scrollTop flag off the last render, but only once it has
  // confirmed that render actually was a "tables" call: otherwise a stale
  // earlier "tables" call sitting at the end of s.calls would make a false
  // assertion pass vacuously if a handler stopped re-rendering.
  const lastScrollTop = () => {
    const last = s.calls[s.calls.length - 1];
    expect(last.name).toBe("tables");
    return last.args[1];
  };

  c.handlers.onToggleSelect(0, 1);
  expect(lastScrollTop()).toBe(false);

  c.handlers.onQuery(0, "q");
  expect(lastScrollTop()).toBe(false);

  c.handlers.onSelectTable(0);
  expect(lastScrollTop()).toBe(true);

  c.handlers.onPage(0, 0);
  expect(lastScrollTop()).toBe(true);

  // jumpToMonth ends in setPage (review/state.ts), so it is a page change too.
  c.handlers.onQuery(0, "");
  c.handlers.onJumpToMonth(0, "2024-01");
  expect(lastScrollTop()).toBe(true);
});

test("report then skip while the report is in flight is a no-op; single exit", async () => {
  const s = fakeScreens();
  let resolveDonate: (r: DonateResult) => void = () => undefined;
  const donations: { key: string; json: string }[] = [];
  const logs: Milestone[] = [];
  const exits: [number, string][] = [];
  const host: Host = {
    ready: Promise.resolve("en"),
    donate: (key, json) => { donations.push({ key, json }); return new Promise<DonateResult>((resolve) => { resolveDonate = resolve; }); },
    exit: (code, info) => { exits.push([code, info]); },
    log: (m) => { logs.push(m); },
    resize: () => undefined,
  };
  const deps: ControllerDeps = {
    host,
    screens: s.screens,
    loadExport: () => Promise.resolve(exportOk),
    runExtraction: () => Promise.resolve({ tables: [], errors: {} }),
    sessionId: "111",
    appVersion: "0.1.0",
    userAgent: "UA",
    now: () => "2026-09-06T00:00:00Z",
    yieldToUi: () => Promise.resolve(),
  };
  const c = new Controller(deps);
  c.start();
  c.handlers.onFile(file);
  await tick(); await tick();
  c.handlers.onReport();
  c.handlers.onSkipReport();
  resolveDonate({ ok: true, status: 200 });
  await tick(); await tick();
  expect(exits).toEqual([[1, "error"]]);
  expect(logs.filter((l) => l === "error_report_sent").length).toBe(1);
  expect(logs).not.toContain("error_report_skipped");
  expect(logs.filter((l) => l === "exited").length).toBe(1);
});

test("a throw rendering the done screen cannot undo a delivered donation", async () => {
  const { c, s, h } = make();
  s.raw.done = () => { throw new Error("kaboom"); };
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  c.handlers.onDonate();
  await tick(); await tick();
  expect(h.exits).toEqual([[0, "completed"]]);
  expect(s.calls.filter((x) => x.name === "error")).toEqual([]);
  expect(h.logs).toContain("donate_succeeded");
});

test("a throw rendering the sending screen takes the error path, nothing donated", async () => {
  const { c, s, h } = make();
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  s.raw.sending = () => { throw new Error("kaboom"); };
  // Nothing catches this synchronously; in the app it reaches window.onerror,
  // which calls onUnhandled().
  expect(() => c.handlers.onDonate()).toThrow();
  c.onUnhandled();
  await tick(); await tick();
  expect(h.donations).toEqual([]);
  expect(s.calls[s.calls.length - 1]).toEqual({ name: "error", args: ["unexpected"] });
  expect(h.exits).toEqual([]);
  c.handlers.onSkipReport();
  expect(h.exits).toEqual([[1, "error"]]);
});

test("onUnhandled exits once even when every screen throws", () => {
  const { c, s, h } = make();
  s.raw.error = () => { throw new Error("no error screen"); };
  s.raw.incomplete = () => { throw new Error("no incomplete screen"); };
  c.onUnhandled();
  c.onUnhandled();
  expect(h.exits).toEqual([[1, "error"]]);
  expect(h.logs.filter((l) => l === "exited").length).toBe(1);
});

test("onUnhandled after a completed donation is a no-op", async () => {
  const { c, h } = make();
  c.handlers.onFile(file); await tick(); await tick();
  c.handlers.onProceed();
  c.handlers.onDonate();
  await tick(); await tick();
  expect(h.exits).toEqual([[0, "completed"]]);
  c.onUnhandled();
  expect(h.exits).toEqual([[0, "completed"]]);
});

test("EXIT table", () => {
  expect(EXIT).toEqual({ completed: [0, "completed"], error: [1, "error"], donationFailed: [3, "donation_failed"], uploadRejected: [4, "upload_rejected"] });
});
