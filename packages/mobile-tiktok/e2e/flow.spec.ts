import { test, expect, Page, FrameLocator } from "@playwright/test";
import { existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIX = join(__dirname, "..", "fixtures", "generated");
// Real-export-shaped, git-ignored (ADR-0041/ADR-0014): present only on a
// machine someone dropped it on, never in a fresh clone or CI.
const LARGE_TXT = join(__dirname, "..", "fixtures", "ddp", "large_txt_en.zip");

interface HostState { donations: { key: string; json_string: string }[]; logs: string[]; exits: { code: number; info: string }[]; initialized: boolean; inits: number }

async function hostState(page: Page): Promise<HostState> {
  return page.evaluate(() => (window as unknown as { __host: HostState }).__host);
}

// The app renders its last screen and only then posts the exit, which reaches
// the top page as a port message a turn later. Waiting on the heading alone can
// therefore read __host before the exit has landed.
async function waitForExit(page: Page): Promise<void> {
  await page.waitForFunction(() => (window as unknown as { __host: HostState }).__host.exits.length > 0);
}

async function open(page: Page, query = ""): Promise<FrameLocator> {
  await page.goto("/fake-host.html" + query);
  const app = page.frameLocator("#app");
  await expect(page.locator("#state")).toHaveText("initialized");
  return app;
}

async function pick(_page: Page, app: FrameLocator, zip: string): Promise<void> {
  const input = app.locator("input[type=file]");
  await input.setInputFiles(join(FIX, zip));
}

// fake-host.html (like the real host) sets the iframe's height directly from
// the "resize" message, so it is readable straight off the element.
async function iframeHeightPx(page: Page): Promise<number> {
  return page.evaluate(() => {
    const el = document.getElementById("app") as HTMLIFrameElement;
    return parseInt(el.style.height || "0", 10);
  });
}

test("donate after removing one row", async ({ page }) => {
  const app = await open(page, "?locale=nl");
  await pick(page, app, "json_en.zip");
  await expect(app.locator("h1")).toHaveText("Je TikTok-gegevens");
  await expect(app.locator("[data-role=table-select] option").first()).toContainText("(");
  // Tick one row and remove the selection: no confirm dialog on this path.
  // The input itself is visually hidden (iOS 12's own checkbox rendering is
  // too faint to notice); a participant taps the drawn .mt-box, which the
  // wrapping label forwards to the input exactly as a real device does.
  await app.locator(".mt-row").first().locator(".mt-box").click();
  await app.locator("[data-action=remove-selected]").click();
  await expect(app.locator("[data-action=undo]")).toBeVisible();
  await expect(app.locator("[data-action=remove-selected]")).toHaveCount(0);
  await app.locator("[data-action=proceed]").click();
  await expect(app.locator("h1")).toHaveText("Klaar om te doneren?");
  await app.locator("[data-action=donate]").click();
  await expect(app.locator("h1")).toHaveText("Bedankt");
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.exits).toEqual([{ code: 0, info: "completed" }]);
  expect(h.donations).toHaveLength(1);
  expect(h.donations[0].key).toMatch(/^\d+-tiktok$/);
  const payload = JSON.parse(h.donations[0].json_string) as { [k: string]: unknown }[];
  const first = payload[0];
  expect(first["deleted row count"]).toBe("1");
  expect(h.logs.slice(0, 4)).toEqual(["file_selected", "archive_read", "extracted", "review_shown"]);
});

test("Next table steps through the tables via the dropdown", async ({ page }) => {
  const app = await open(page);
  await pick(page, app, "json_en.zip");
  await expect(app.locator("[data-role=table-select]")).toHaveValue("0");
  await app.locator("[data-action=next-table]").click();
  await expect(app.locator("[data-role=table-select]")).toHaveValue("1");
});

test("search and bulk delete", async ({ page }) => {
  const app = await open(page);
  await pick(page, app, "json_en.zip");
  await app.locator("[data-role=table-select]").selectOption({ index: 2 });
  await expect(app.locator("[data-role=page-label]").first()).toHaveText("Page 1 of 1");
  await expect(app.locator("[data-role=month-select]")).toBeVisible();
  await app.locator("input[type=search]").fill("https://");
  await expect(app.locator("[data-action=remove-matches]")).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await app.locator("[data-action=remove-matches]").click();
  await expect(app.locator("text=No rows to show.")).toBeVisible();
  await app.locator("[data-action=undo]").click();
  await expect(app.locator(".mt-row").first()).toBeVisible();
});

test("decline records the literal", async ({ page }) => {
  const app = await open(page);
  await pick(page, app, "txt_en.zip");
  await app.locator("[data-action=proceed]").click();
  await app.locator("[data-action=decline]").click();
  await expect(app.locator("h1")).toHaveText("Thank you");
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.donations[0].json_string).toBe('{"status": "data_submission declined"}');
  expect(h.exits[0].code).toBe(0);
});

test("not a TikTok zip offers retry, stop exits 4", async ({ page }) => {
  const app = await open(page);
  await app.locator("input[type=file]").setInputFiles({ name: "x.zip", mimeType: "application/zip", buffer: Buffer.from("PK not really") });
  await expect(app.locator("h1")).toHaveText("Something went wrong");
  await app.locator("[data-action=stop]").click();
  await expect(app.locator("h1")).toHaveText("Task not completed");
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.exits).toEqual([{ code: 4, info: "upload_rejected" }]);
  expect(h.donations).toHaveLength(0);
});

test("sparse export with no tables reports without data", async ({ page }) => {
  const app = await open(page);
  await pick(page, app, "json_sparse.zip");
  await expect(app.locator("[data-action=report]")).toBeVisible();
  await app.locator("[data-action=report]").click();
  await expect(app.locator("h1")).toHaveText("Task not completed");
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.donations[0].key).toBe("error-report");
  const report = JSON.parse(h.donations[0].json_string);
  expect(Object.keys(report).sort()).toEqual(["appVersion", "category", "platform", "timestamp", "userAgent"]);
  expect(report.category).toBe("extract_failed");
  expect(h.exits).toEqual([{ code: 1, info: "error" }]);
});

test("donation failure: retry then stop exits 3", async ({ page }) => {
  const app = await open(page, "?fail=1");
  await pick(page, app, "json_en.zip");
  await app.locator("[data-action=proceed]").click();
  await app.locator("[data-action=donate]").click();
  await expect(app.locator("h1")).toHaveText("Sending failed");
  await app.locator("[data-action=retry-donate]").click();
  await expect(app.locator("h1")).toHaveText("Sending failed");
  await app.locator("[data-action=stop]").click();
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.donations).toHaveLength(2);
  expect(h.exits).toEqual([{ code: 3, info: "donation_failed" }]);
});

test("donation completes after a second live-init", async ({ page }) => {
  const app = await open(page);
  // The host builds a fresh MessageChannel on every `app-loaded`; a message
  // from the top page drives the fake host down exactly that path, so the app
  // has to follow the newest port or the donation reply never arrives.
  // The fake host, like the real one, may already have initialized twice by the
  // time the app is up (the iframe load event and `app-loaded` both build a
  // channel), so count from wherever startup left off.
  const before = await page.evaluate(() => (window as unknown as { __host: HostState }).__host.inits);
  await page.evaluate(() => window.postMessage({ action: "app-loaded" }, "*"));
  await page.waitForFunction((n) => (window as unknown as { __host: HostState }).__host.inits === n + 1, before);
  await pick(page, app, "json_en.zip");
  await app.locator("[data-action=proceed]").click();
  await app.locator("[data-action=donate]").click();
  await expect(app.locator("h1")).toHaveText("Thank you");
  await waitForExit(page);
  const h = await hostState(page);
  expect(h.inits).toBe(before + 1);
  expect(h.donations).toHaveLength(1);
  expect(h.exits).toEqual([{ code: 0, info: "completed" }]);
});

test("the iframe shrinks back after switching from a large table to a small one", async ({ page }) => {
  test.skip(!existsSync(LARGE_TXT), "needs a real export with 50+ rows locally at fixtures/ddp/large_txt_en.zip (git-ignored, not present in a fresh clone or CI)");
  const app = await open(page);
  await app.locator("input[type=file]").setInputFiles(LARGE_TXT);
  await expect(app.locator("h1")).toHaveText("Your TikTok data");
  const select = app.locator("[data-role=table-select]");

  const watchValue = await select.locator("option", { hasText: "Watch history" }).first().getAttribute("value");
  await select.selectOption(watchValue as string);
  // The tables screen measures itself again on the next tick after paint
  // (screens.ts's follow-up afterRender), so wait for that resize to land
  // rather than a fixed sleep.
  await page.waitForFunction(() => {
    const el = document.getElementById("app") as HTMLIFrameElement;
    return parseInt(el.style.height || "0", 10) > 500;
  });
  const tall = await iframeHeightPx(page);

  const summaryValue = await select.locator("option", { hasText: "activity summary" }).first().getAttribute("value");
  await select.selectOption(summaryValue as string);
  await page.waitForFunction((was) => {
    const el = document.getElementById("app") as HTMLIFrameElement;
    const h = parseInt(el.style.height || "0", 10);
    return h > 0 && h < was;
  }, tall);
  const short = await iframeHeightPx(page);
  expect(short).toBeLessThan(tall);
});
