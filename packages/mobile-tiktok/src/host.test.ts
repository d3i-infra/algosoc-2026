import { connectHost } from "./host";

type Listener = (e: { data: unknown; ports?: unknown[] }) => void;

function fakeWindow() {
  const listeners: Listener[] = [];
  const parentPosts: unknown[] = [];
  const win = {
    addEventListener: (_: string, fn: Listener) => listeners.push(fn),
    parent: { postMessage: (m: unknown) => parentPosts.push(m) },
  } as unknown as Window;
  return { win, listeners, parentPosts };
}

function fakePort() {
  const posts: unknown[] = [];
  const port = { postMessage: (m: unknown) => posts.push(m), onmessage: null as null | ((e: { data: unknown }) => void) };
  return { port, posts };
}

function fakeDoc(height: number) {
  return { body: { scrollHeight: height } } as unknown as Document;
}

function init(_win: Window, listeners: Listener[], port: unknown, locale = "nl") {
  for (const fn of listeners) fn({ data: { action: "live-init", locale }, ports: [port] });
}

test("posts app-loaded on connect", () => {
  const { win, parentPosts } = fakeWindow();
  connectHost(win, fakeDoc(100));
  expect(parentPosts).toEqual([{ action: "app-loaded" }]);
});

test("ready resolves with the locale and sends initialized", async () => {
  const { win, listeners } = fakeWindow();
  const { port, posts } = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, port, "nl-NL");
  expect(await host.ready).toBe("nl");
  expect(posts[0]).toEqual({ __type__: "CommandSystemEvent", name: "initialized" });
});

test("unknown locale falls back to en", async () => {
  const { win, listeners } = fakeWindow();
  const { port } = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, port, "de");
  expect(await host.ready).toBe("en");
});

test("donate resolves only on the reply with the same key", async () => {
  const { win, listeners } = fakeWindow();
  const { port, posts } = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, port);
  await host.ready;
  let settled = false;
  const p = host.donate("123-tiktok", "{}").then((r) => { settled = true; return r; });
  expect(posts[1]).toEqual({ __type__: "CommandSystemDonate", key: "123-tiktok", json_string: "{}" });
  port.onmessage!({ data: { __type__: "DonateSuccess", key: "other", status: 200 } });
  await Promise.resolve();
  expect(settled).toBe(false);
  port.onmessage!({ data: { __type__: "DonateError", key: "123-tiktok", status: 500, error: "boom" } });
  expect(await p).toEqual({ ok: false, status: 500, error: "boom" });
});

test("donate success", async () => {
  const { win, listeners } = fakeWindow();
  const { port } = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, port);
  await host.ready;
  const p = host.donate("k", "{}");
  port.onmessage!({ data: { __type__: "DonateSuccess", key: "k", status: 200 } });
  expect(await p).toEqual({ ok: true, status: 200 });
});

test("exit, log and resize shapes", async () => {
  const { win, listeners, parentPosts } = fakeWindow();
  const { port, posts } = fakePort();
  const host = connectHost(win, fakeDoc(640));
  init(win, listeners, port);
  await host.ready;
  host.log("review_shown");
  host.exit(0, "completed");
  host.resize();
  expect(posts[1]).toEqual({ __type__: "CommandSystemLog", json_string: JSON.stringify({ level: "info", message: "review_shown" }) });
  expect(posts[2]).toEqual({ __type__: "CommandSystemExit", code: 0, info: "completed" });
  expect(parentPosts[1]).toEqual({ action: "resize", height: 640 + 48 });
});

test("resize without a measure uses the old body-scrollHeight behaviour", () => {
  const { win, parentPosts } = fakeWindow();
  const host = connectHost(win, fakeDoc(640));
  host.resize();
  expect(parentPosts[1]).toEqual({ action: "resize", height: 640 + 48 });
});

test("resize with a measure posts its ceiling instead of the body height", () => {
  const { win, parentPosts } = fakeWindow();
  // The body is never shorter than the iframe once the host has grown it, so a
  // caller that can measure its own content passes that instead.
  const host = connectHost(win, fakeDoc(9999), () => 300.4);
  host.resize();
  expect(parentPosts[1]).toEqual({ action: "resize", height: 349 });
});

test("log before live-init is dropped, not queued", async () => {
  const { win, listeners } = fakeWindow();
  const { port, posts } = fakePort();
  const host = connectHost(win, fakeDoc(100));
  host.log("file_selected");
  init(win, listeners, port);
  await host.ready;
  expect(posts.length).toBe(1);
});

test("a second live-init adopts the new port", async () => {
  const { win, listeners } = fakeWindow();
  const a = fakePort();
  const b = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, a.port, "en");
  await host.ready;
  init(win, listeners, b.port, "nl");
  expect(b.posts[0]).toEqual({ __type__: "CommandSystemEvent", name: "initialized" });
  const p = host.donate("k", "{}");
  expect(a.posts.length).toBe(1);
  expect(b.posts[1]).toEqual({ __type__: "CommandSystemDonate", key: "k", json_string: "{}" });
  b.port.onmessage!({ data: { __type__: "DonateSuccess", key: "k", status: 200 } });
  expect(await p).toEqual({ ok: true, status: 200 });
});

test("a donation pending across the switch fails instead of hanging", async () => {
  const { win, listeners } = fakeWindow();
  const a = fakePort();
  const b = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, a.port);
  await host.ready;
  const p = host.donate("k", "{}");
  init(win, listeners, b.port);
  expect(await p).toEqual({ ok: false, status: 0, error: "" });
  // The old port's reply is ignored: the donation is already settled.
  a.port.onmessage!({ data: { __type__: "DonateSuccess", key: "k", status: 200 } });
  expect(await p).toEqual({ ok: false, status: 0, error: "" });
});

test("ready resolves once, with the first locale", async () => {
  const { win, listeners } = fakeWindow();
  const a = fakePort();
  const b = fakePort();
  const host = connectHost(win, fakeDoc(100));
  init(win, listeners, a.port, "nl-NL");
  init(win, listeners, b.port, "en-GB");
  expect(await host.ready).toBe("nl");
});
