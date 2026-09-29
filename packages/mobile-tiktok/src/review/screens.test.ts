import { Screens, ScreenHandlers } from "./screens";
import { ReviewState } from "./state";
import type { Table } from "../extract";

function handlers(): ScreenHandlers & { calls: string[] } {
  const calls: string[] = [];
  const h = {} as ScreenHandlers & { calls: string[] };
  h.calls = calls;
  for (const name of ["onFile", "onSelectTable", "onQuery", "onToggleSelect", "onToggleSelectAll", "onDeleteSelected", "onPage", "onUndo", "onProceed", "onBack", "onDonate", "onDecline", "onRetryDonate", "onStop", "onReport", "onSkipReport"]) {
    (h as unknown as { [k: string]: (...a: unknown[]) => void })[name] = (...a: unknown[]) => calls.push(name + ":" + a.map(String).join(","));
  }
  return h;
}

function setup(locale: "en" | "nl" = "en") {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const h = handlers();
  let renders = 0;
  const s = new Screens(root, locale, h, () => renders++);
  return { root, h, s, renders: () => renders };
}

function watchHistory(n: number): Table {
  const rows: string[][] = [];
  for (let i = 0; i < n; i++) {
    const month = 1 + Math.floor(i / 30);
    const mm = month < 10 ? "0" + month : String(month);
    rows.push(["2024-" + mm + "-01 09:00:00", "https://www.tiktokv.com/share/video/" + i + "/"]);
  }
  return { id: "tiktok_watch_history", columns: ["Date", "Link"], rows };
}

const searches: Table = { id: "tiktok_searches", columns: ["Date", "SearchTerm"], rows: [["2024-01-01", "q"]] };
const shares: Table = { id: "tiktok_share_history", columns: ["Date", "SharedContent", "Link", "Method"], rows: [["2024-01-01 09:00:00", "video", "https://x/1", "Copy"]] };

function rowsIn(root: HTMLElement): HTMLElement[] {
  return Array.prototype.slice.call(root.querySelectorAll(".mt-row")) as HTMLElement[];
}

function pageLabel(root: HTMLElement): string {
  return (root.querySelector("[data-role=page-label]") as HTMLElement).textContent || "";
}

function summary(root: HTMLElement): string {
  return (root.querySelector("[data-role=summary]") as HTMLElement).textContent || "";
}

// The removed count is a span of its own, greyed as the desktop greys it.
function deletedPart(root: HTMLElement): string {
  const el = root.querySelector("[data-role=deleted]") as HTMLElement | null;
  return el === null ? "" : el.textContent || "";
}

test("intro shows the file input and reports a chosen file", () => {
  const { root, h, s } = setup("nl");
  s.intro();
  expect(root.textContent).toContain("Doneer uw TikTok-gegevens");
  const input = root.querySelector("input[type=file]") as HTMLInputElement;
  const file = new File(["x"], "a.zip");
  Object.defineProperty(input, "files", { value: [file] });
  input.dispatchEvent(new Event("change"));
  expect(h.calls).toEqual(["onFile:[object File]"]);
});

test("a select lists every table with its kept count and switches table on change", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(2), searches]);
  s.tables(state);
  const sel = root.querySelector("select[data-role=table-select]") as HTMLSelectElement;
  expect(sel.options.length).toBe(2);
  expect(sel.options[0].textContent).toBe("Watch history (2 rows)");
  expect(sel.options[1].textContent).toBe("Searches (1 row)");
  expect(sel.value).toBe("0");
  expect(root.querySelector("[data-tab]")).toBeNull();
  sel.value = "1";
  sel.dispatchEvent(new Event("change"));
  expect(h.calls).toContain("onSelectTable:1");
});

test("a large table's select option shows a locale-grouped kept count", () => {
  const { root, s } = setup("en");
  const state = new ReviewState([watchHistory(200000), searches]);
  s.tables(state);
  const sel = root.querySelector("select[data-role=table-select]") as HTMLSelectElement;
  expect(sel.options[0].textContent).toBe("Watch history (200,000 rows)");
});

test("only the current page of rows is rendered, with the page label and paging handlers", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(52)]);
  s.tables(state);
  expect(rowsIn(root).length).toBe(25);
  expect(rowsIn(root)[0].getAttribute("data-row")).toBe("0");
  expect(pageLabel(root)).toBe("1/3");
  (root.querySelector("[data-action=next-page]") as HTMLElement).click();
  expect(h.calls).toContain("onPage:0,1");
  state.setPage(0, 2);
  s.tables(state);
  expect(rowsIn(root).length).toBe(2);
  expect(rowsIn(root)[0].getAttribute("data-row")).toBe("50");
  expect(pageLabel(root)).toBe("3/3");
  (root.querySelector("[data-action=prev-page]") as HTMLElement).click();
  expect(h.calls).toContain("onPage:0,1");
});

test("there is one page bar, below the rows, as on the desktop", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(52)]));
  expect(root.querySelectorAll("[data-action=prev-page]").length).toBe(1);
  expect(root.querySelectorAll("[data-action=next-page]").length).toBe(1);
  const bars = Array.prototype.slice.call(root.querySelectorAll("[data-role=page-bar]")) as HTMLElement[];
  expect(bars.length).toBe(1);
  expect(bars[0].className).not.toContain("invisible");
  const rowsHost = root.querySelector("[data-role=rows]") as HTMLElement;
  expect(rowsHost.compareDocumentPosition(bars[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("the page bar is out of the way when everything fits on one page", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(6)]);
  s.tables(state);
  const bars = Array.prototype.slice.call(root.querySelectorAll("[data-role=page-bar]")) as HTMLElement[];
  expect(bars.length).toBe(1);
  expect(bars[0].className).toContain("invisible");
  expect(pageLabel(root)).toBe("1/1");
});

test("a checkbox tap leaves the row nodes and any expansion in place", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(26)]);
  s.tables(state);
  const firstRow = rowsIn(root)[0];
  (firstRow.querySelector("[data-role=cell]") as HTMLElement).click();
  state.toggleSelected(0, 1);
  s.tables(state);
  expect(rowsIn(root)[0]).toBe(firstRow);
  expect(firstRow.getAttribute("data-expanded")).toBe("true");
  expect((rowsIn(root)[1].querySelector("input[type=checkbox]") as HTMLInputElement).checked).toBe(true);
  expect((rowsIn(root)[0].querySelector("input[type=checkbox]") as HTMLInputElement).checked).toBe(false);
  // A page change does rebuild them.
  state.setPage(0, 1);
  s.tables(state);
  expect(rowsIn(root)[0]).not.toBe(firstRow);
});

test("expanding a row reports the new height to the host", () => {
  const { root, s, renders } = setup();
  s.tables(new ReviewState([watchHistory(3)]));
  const before = renders();
  (rowsIn(root)[0].querySelector("[data-role=cell]") as HTMLElement).click();
  expect(renders()).toBe(before + 1);
  (rowsIn(root)[0].querySelector("[data-role=cell]") as HTMLElement).click();
  expect(renders()).toBe(before + 2);
});

test("a checkbox is hidden and drawn by a sibling box the CSS keys on, surviving an in-place re-render", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(3)]);
  s.tables(state);
  const box = rowsIn(root)[0].querySelector("input[type=checkbox]") as HTMLInputElement;
  expect(box.className).toContain("mt-visually-hidden");
  const tick = box.nextElementSibling as HTMLElement;
  expect(tick).not.toBeNull();
  expect(tick.className).toContain("mt-box");
  expect(box.checked).toBe(false);

  // Same table, same page, same rows: renderRows takes the in-place fast
  // path (screens.ts reuses the row nodes and only flips `checked`), which is
  // exactly the path that would silently separate the input from its .mt-box
  // if a future change rebuilt the row without keeping them adjacent.
  state.toggleSelected(0, 0);
  s.tables(state);
  const again = rowsIn(root)[0].querySelector("input[type=checkbox]") as HTMLInputElement;
  expect(again).toBe(box);
  expect(again.checked).toBe(true);
  expect(again.nextElementSibling).toBe(tick);
  expect((again.nextElementSibling as HTMLElement).className).toContain("mt-box");
});

test("each checkbox is labelled with its row's first cell", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(3)]));
  const box = rowsIn(root)[0].querySelector("input[type=checkbox]") as HTMLInputElement;
  expect(box.getAttribute("aria-label")).toBe("2024-01-01 09:00:00");
});

test("a row checkbox reports the underlying row index and shows the selection", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(3)]);
  s.tables(state);
  const box = rowsIn(root)[1].querySelector("input[type=checkbox][data-role=select]") as HTMLInputElement;
  expect(box.checked).toBe(false);
  box.checked = true;
  box.dispatchEvent(new Event("change"));
  expect(h.calls).toContain("onToggleSelect:0,1");
  state.toggleSelected(0, 1);
  s.tables(state);
  const again = rowsIn(root)[1].querySelector("input[type=checkbox]") as HTMLInputElement;
  expect(again.checked).toBe(true);
  expect((rowsIn(root)[0].querySelector("input[type=checkbox]") as HTMLInputElement).checked).toBe(false);
});

test("remove-selected appears only with a selection and needs no confirm", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(3)]);
  s.tables(state);
  expect(root.querySelector("[data-action=remove-selected]")).toBeNull();
  state.toggleSelected(0, 0);
  state.toggleSelected(0, 2);
  s.tables(state);
  const btn = root.querySelector("[data-action=remove-selected]") as HTMLElement;
  expect(btn.textContent).toBe("Delete 2");
  btn.click();
  expect(h.calls).toContain("onDeleteSelected:0");
  state.clearSelection(0);
  s.tables(state);
  expect(root.querySelector("[data-action=remove-selected]")).toBeNull();
});

test("tapping the cells expands and collapses the row", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const row = rowsIn(root)[0];
  const cells = row.querySelector("[data-role=cell]") as HTMLElement;
  expect(row.hasAttribute("data-expanded")).toBe(false);
  cells.click();
  expect(row.getAttribute("data-expanded")).toBe("true");
  cells.click();
  expect(row.hasAttribute("data-expanded")).toBe(false);
});

test("every cell of the row is rendered in its own column", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([{ id: "tiktok_share_history", columns: ["Date", "SharedContent", "Link", "Method"], rows: [["2024-01-01", "video", "https://x/1", "Copy"]] }]));
  const cells = rowsIn(root)[0].querySelectorAll(".mt-cell");
  expect(cells.length).toBe(4);
  expect(cells[0].className).toContain("font-table-row");
  expect(cells[0].textContent).toBe("2024-01-01");
  expect(cells[2].textContent).toBe("https://x/1");
});

test("search is debounced through onQuery and the input node survives an update", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(52), searches]);
  s.tables(state);
  const search = root.querySelector("input[type=search]") as HTMLInputElement;
  search.value = "20";
  search.dispatchEvent(new Event("input"));
  expect(h.calls.filter((c) => c.indexOf("onQuery:0,20") === 0).length).toBe(1);
  state.setQuery(0, "video/5");
  s.tables(state);
  expect(root.querySelector("input[type=search]")).toBe(search);
  state.activeIndex = 1;
  s.tables(state);
  expect(root.querySelector("input[type=search]")).not.toBe(search);
});

test("an in-place update re-renders the rows, the counts and the page label", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(52), searches]);
  s.tables(state);
  const search = root.querySelector("input[type=search]") as HTMLInputElement;
  const sel = root.querySelector("select[data-role=table-select]") as HTMLSelectElement;
  state.setPage(0, 2);
  s.tables(state);
  expect(root.querySelector("input[type=search]")).toBe(search);
  expect(root.querySelector("select[data-role=table-select]")).toBe(sel);
  expect(rowsIn(root).length).toBe(2);
  expect(pageLabel(root)).toBe("3/3");
  state.toggleSelected(0, 50);
  state.deleteSelected(0);
  s.tables(state);
  expect(sel.options[0].textContent).toBe("Watch history (51 rows)");
  expect(summary(root)).toBe("2 columns, 51 rows");
  expect(deletedPart(root)).toBe(", 1 deleted");
  expect(pageLabel(root)).toBe("3/3");
  expect(root.querySelector("[data-action=undo]")).not.toBeNull();
});

test("an emptied table shows the no-data line", () => {
  const { root, s } = setup();
  const state = new ReviewState([searches]);
  s.tables(state);
  state.setQuery(0, "nothing-matches-this");
  s.tables(state);
  expect(rowsIn(root).length).toBe(0);
  const empty = root.querySelector("[data-role=rows] tbody td") as HTMLElement;
  expect(empty.textContent).toBe("no data");
  expect(empty.className).toContain("text-grey2");
  expect(empty.getAttribute("colspan")).toBe("3");
  expect(pageLabel(root)).toBe("1/1");
});

test("the review screen scrolls as one page: no inner scroll container", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(52)]));
  // The windowed list gave its container a measured pixel height and an
  // absolutely positioned spacer; the page now flows on its own.
  const sized = (Array.prototype.slice.call(root.querySelectorAll("div")) as HTMLElement[])
    .filter((d) => d.style.height !== "" || d.style.overflowY !== "");
  expect(sized).toEqual([]);
  // The one scroll container is the table's own, which the desktop has too.
  const scrollers = (Array.prototype.slice.call(root.querySelectorAll("div")) as HTMLElement[])
    .filter((d) => d.className.indexOf("overflow-x-auto") >= 0);
  expect(scrollers.length).toBe(1);
});

test("the primary button keeps the desktop look and is not full width, and is alone", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const proceed = root.querySelector("[data-action=proceed]") as HTMLElement;
  expect(proceed.className).toContain("inline-block");
  expect(proceed.className).toContain("bg-primary");
  expect(proceed.className).toContain("font-button");
  expect(proceed.className).not.toContain("w-full");
  expect(root.querySelector("[data-action=restart]")).toBeNull();
  expect(root.querySelector("[data-action=back]")).toBeNull();
});

test("the tables screen primary button reads Show summary before sharing", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const proceed = root.querySelector("[data-action=proceed]") as HTMLElement;
  expect(proceed.textContent).toBe("Show summary before sharing");
});

const tick = () => new Promise((r) => setTimeout(r, 0));

test("the screen top scrolls into view after a table switch or a page change, not after a toggle or a search keystroke", async () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(52), searches]);
  const calls: Element[] = [];
  type WithScroll = { scrollIntoView?: () => void };
  const original = (Element.prototype as WithScroll).scrollIntoView;
  (Element.prototype as WithScroll).scrollIntoView = function (this: Element) { calls.push(this); };
  try {
    s.tables(state);
    expect(calls.length).toBe(0);

    // Page change on the same table takes the in-place path, which scrolls
    // synchronously (there is no resize to wait out there).
    state.setPage(0, 1);
    s.tables(state, true);
    expect(calls.length).toBe(1);
    expect(calls[0]).toBe(root.firstChild);

    // A checkbox toggle re-renders in place too, but is not a scroll trigger.
    state.toggleSelected(0, 25);
    s.tables(state);
    expect(calls.length).toBe(1);

    // Nor is a search keystroke.
    state.setQuery(0, "video");
    s.tables(state);
    expect(calls.length).toBe(1);

    // A table switch takes the full-rebuild path, where the scroll waits for
    // the follow-up tick that also re-measures the frame after a resize.
    state.activeIndex = 1;
    s.tables(state, true);
    expect(calls.length).toBe(1);
    await tick();
    expect(calls.length).toBe(2);
  } finally {
    (Element.prototype as WithScroll).scrollIntoView = original;
  }
});

test("confirm, done, failed, error, incomplete render and call back", () => {
  const { root, h, s, renders } = setup();
  const state = new ReviewState([searches]);
  s.confirm(state);
  (root.querySelector("[data-action=donate]") as HTMLElement).click();
  (root.querySelector("[data-action=decline]") as HTMLElement).click();
  s.failed();
  (root.querySelector("[data-action=retry-donate]") as HTMLElement).click();
  (root.querySelector("[data-action=stop]") as HTMLElement).click();
  s.error("extract_failed");
  (root.querySelector("[data-action=report]") as HTMLElement).click();
  (root.querySelector("[data-action=skip]") as HTMLElement).click();
  s.retry("not_tiktok");
  expect(root.textContent).toContain("does not look like a TikTok export");
  s.done();
  expect(root.textContent).toContain("Thank you");
  s.incomplete();
  expect(root.textContent).toContain("Task not completed");
  expect(h.calls).toEqual(["onDonate:", "onDecline:", "onRetryDonate:", "onStop:", "onReport:", "onSkipReport:"]);
  expect(renders()).toBe(6);
});

test("the tables screen reports its height again on the next tick", async () => {
  const { root, s, renders } = setup();
  s.tables(new ReviewState([searches]));
  expect(root.querySelector(".mt-row")).not.toBeNull();
  const first = renders();
  await new Promise((r) => setTimeout(r, 0));
  expect(renders()).toBe(first + 1);
});

test("the selector is left out for a single table and carries the position for many", () => {
  const one = setup();
  one.s.tables(new ReviewState([watchHistory(2)]));
  expect(one.root.querySelector("[data-role=table-select]")).toBeNull();
  expect(one.root.textContent).not.toContain("Your data is divided over");

  const many = setup();
  const state = new ReviewState([watchHistory(2), searches, shares]);
  many.s.tables(state);
  expect(many.root.querySelector("[data-role=table-select]")).not.toBeNull();
  expect(many.root.textContent).toContain("Your data is divided over 3 tables");
  expect((many.root.querySelector("[data-role=table-position]") as HTMLElement).textContent).toBe("1 of 3");
  state.activeIndex = 2;
  many.s.tables(state);
  expect((many.root.querySelector("[data-role=table-position]") as HTMLElement).textContent).toBe("3 of 3");
});

test("the step buttons walk the tables and are disabled at the ends", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(2), searches, shares]);
  s.tables(state);
  const prev = () => root.querySelector("[data-action=prev-table]") as HTMLButtonElement;
  const next = () => root.querySelector("[data-action=next-table]") as HTMLButtonElement;
  expect(prev().disabled).toBe(true);
  expect(prev().className).toContain("opacity-40");
  expect(next().disabled).toBe(false);
  expect(next().getAttribute("aria-label")).toBe("Next table");
  expect(prev().getAttribute("aria-label")).toBe("Previous table");
  next().click();
  expect(h.calls).toContain("onSelectTable:1");

  state.activeIndex = 1;
  s.tables(state);
  expect(prev().disabled).toBe(false);
  expect(next().disabled).toBe(false);
  prev().click();
  expect(h.calls).toContain("onSelectTable:0");

  state.activeIndex = 2;
  s.tables(state);
  expect(next().disabled).toBe(true);
  expect(next().className).toContain("opacity-40");
});

test("the header cells carry the config's translated column names", () => {
  const en = setup("en");
  en.s.tables(new ReviewState([shares]));
  const heads = (root: HTMLElement) => (Array.prototype.slice.call(root.querySelectorAll("thead th div")) as HTMLElement[]).map((d) => d.textContent);
  expect(heads(en.root)).toEqual(["Date", "Shared content", "Link", "Method"]);

  const nl = setup("nl");
  nl.s.tables(new ReviewState([shares]));
  expect(heads(nl.root)).toEqual(["Datum en tijd", "Gedeelde inhoud", "Link", "Methode"]);

  // A table the config does not know falls back to the raw column names.
  const raw = setup();
  raw.s.tables(new ReviewState([{ id: "not_in_config", columns: ["Alpha", "Beta"], rows: [["a", "b"]] }]));
  expect(heads(raw.root)).toEqual(["Alpha", "Beta"]);
});

test("the header tick box reports select-all and follows the visible selection", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(3)]);
  s.tables(state);
  const all = () => root.querySelector("input[data-role=select-all]") as HTMLInputElement;
  expect(all().getAttribute("aria-label")).toBe("Select all rows");
  expect(all().checked).toBe(false);
  all().dispatchEvent(new Event("change"));
  expect(h.calls).toContain("onToggleSelectAll:0");

  state.selectAllVisible(0);
  s.tables(state);
  expect(all().checked).toBe(true);
  expect((Array.prototype.slice.call(root.querySelectorAll("input[data-role=select]")) as HTMLInputElement[]).every((b) => b.checked)).toBe(true);

  state.clearSelection(0);
  s.tables(state);
  expect(all().checked).toBe(false);
  expect((Array.prototype.slice.call(root.querySelectorAll("input[data-role=select]")) as HTMLInputElement[]).some((b) => b.checked)).toBe(false);
});

test("the pagination steps to the first, previous, next and last page and stops at the ends", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(60)]);
  s.tables(state);
  const at = (action: string) => root.querySelector("[data-action=" + action + "]") as HTMLButtonElement;
  expect(pageLabel(root)).toBe("1/3");
  expect(at("first-page").disabled).toBe(true);
  expect(at("prev-page").disabled).toBe(true);
  expect(at("first-page").className).toContain("text-grey3");
  expect(at("next-page").className).toContain("text-primary");
  at("next-page").click();
  expect(h.calls).toContain("onPage:0,1");
  at("last-page").click();
  expect(h.calls).toContain("onPage:0,2");

  state.setPage(0, 2);
  s.tables(state);
  expect(pageLabel(root)).toBe("3/3");
  expect(at("next-page").disabled).toBe(true);
  expect(at("last-page").disabled).toBe(true);
  at("prev-page").click();
  expect(h.calls).toContain("onPage:0,1");
  at("first-page").click();
  expect(h.calls).toContain("onPage:0,0");
});

test("the summary line reads the columns, the rows, the search and what was removed", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(60)]);
  s.tables(state);
  expect(summary(root)).toBe("2 columns, 60 rows");
  expect(root.querySelector("[data-action=undo]")).toBeNull();

  state.setQuery(0, "video/5");
  s.tables(state);
  // 5, 50-59: eleven of the sixty rows match.
  expect(summary(root)).toBe("2 columns, 11 / 60 rows");

  state.setQuery(0, "");
  state.toggleSelected(0, 0);
  state.deleteSelected(0);
  s.tables(state);
  expect(summary(root)).toBe("2 columns, 59 rows");
  const gone = root.querySelector("[data-role=deleted]") as HTMLElement;
  expect(gone.textContent).toBe(", 1 deleted");
  expect(gone.className).toContain("text-grey2");
  const undo = root.querySelector("[data-action=undo]") as HTMLElement;
  expect(undo.getAttribute("aria-label")).toBe("Undo");
  // The 44px touch target every other control on this screen honours.
  expect(undo.className).toContain("mt-check");
  undo.click();
  expect(h.calls).toContain("onUndo:0");
});

test("an emptied table reads no data in the summary too", () => {
  const { root, s } = setup();
  const state = new ReviewState([searches]);
  state.selectAllVisible(0);
  state.deleteSelected(0);
  s.tables(state);
  expect(summary(root)).toBe("no data");
  expect(deletedPart(root)).toBe(", 1 deleted");
});

test("Undo belongs to the table beside it, not to whatever was deleted last", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(3), searches]);
  s.tables(state);
  expect(root.querySelector("[data-action=undo]")).toBeNull();

  // Delete in the first table, then in the second, then come back. The first
  // table's Undo must still be here and must report its own index.
  state.toggleSelected(0, 0);
  state.deleteSelected(0);
  s.tables(state);
  expect(root.querySelector("[data-action=undo]")).not.toBeNull();

  state.activeIndex = 1;
  state.toggleSelected(1, 0);
  state.deleteSelected(1);
  s.tables(state);
  (root.querySelector("[data-action=undo]") as HTMLElement).click();
  expect(h.calls).toContain("onUndo:1");

  state.activeIndex = 0;
  s.tables(state);
  (root.querySelector("[data-action=undo]") as HTMLElement).click();
  expect(h.calls).toContain("onUndo:0");

  // Nothing left to undo in this table: the control goes away, even though the
  // other table still has an entry on its own stack.
  state.undo(0);
  s.tables(state);
  expect(root.querySelector("[data-action=undo]")).toBeNull();
});

test("columns are sized from their content, and the widest is left the remainder", () => {
  const { root, s } = setup();
  // Date holds "2024-01-01 09:00:00", but a Date column is sized for the date
  // part alone and wraps the time onto a second line, so it asks for 104px
  // rather than 176 and Link - the widest, and the one being read - keeps the
  // remainder instead of being squeezed to four characters.
  s.tables(new ReviewState([watchHistory(2)]));
  const cols = Array.prototype.slice.call(root.querySelectorAll("[data-role=rows] colgroup col")) as HTMLElement[];
  expect(cols.length).toBe(3);
  expect(cols[0].style.width).toBe("44px");
  expect(cols[1].style.width).toBe("104px");   // 10 chars * 8 + 24
  expect(cols[2].style.width).toBe("");        // the widest column takes the rest
  // Two columns still fit the card, so nothing forces a sideways scroll.
  expect((root.querySelector("[data-role=rows]") as HTMLElement).style.minWidth).toBe("");
});

test("Date cells are marked so they wrap to two lines; other cells are not", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const cells = Array.prototype.slice.call(rowsIn(root)[0].querySelectorAll(".mt-cell")) as HTMLElement[];
  expect(cells[0].className).toContain("mt-cell--date");
  expect(cells[0].textContent).toBe("2024-01-01 09:00:00");
  expect(cells[1].className).not.toContain("mt-cell--date");
  // The header of that column rides along, so "Datum en tijd" wraps rather
  // than truncating the column's own name.
  const heads = Array.prototype.slice.call(root.querySelectorAll("thead .mt-cell")) as HTMLElement[];
  expect(heads[0].className).toContain("mt-cell--date");
  expect(heads[1].className).not.toContain("mt-cell--date");

  // The rule keys on the raw config column name, not the translated label, so
  // it holds in Dutch too.
  const nl = setup("nl");
  nl.s.tables(new ReviewState([watchHistory(2)]));
  const nlHeads = Array.prototype.slice.call(nl.root.querySelectorAll("thead .mt-cell")) as HTMLElement[];
  expect(nlHeads[0].textContent).toBe("Datum en tijd");
  expect(nlHeads[0].className).toContain("mt-cell--date");

  // A table with no Date column marks nothing.
  const plain = setup();
  plain.s.tables(new ReviewState([{ id: "tiktok_hashtag", columns: ["HashtagName", "HashtagLink"], rows: [["#a", "https://x/a"]] }]));
  expect(plain.root.querySelector(".mt-cell--date")).toBeNull();
});

test("a short column is never squeezed below its floor and a long one never past its cap", () => {
  const { root, s } = setup();
  const long = "x".repeat(200);
  s.tables(new ReviewState([{ id: "not_in_config", columns: ["A", "Long", "B"], rows: [["1", long, "2"]] }]));
  const cols = Array.prototype.slice.call(root.querySelectorAll("[data-role=rows] colgroup col")) as HTMLElement[];
  // "A" is one character: clamped up to the three-character floor.
  expect(cols[1].style.width).toBe("48px");    // 3 * 8 + 24
  expect(cols[3].style.width).toBe("48px");
  // The 200-character column is the widest, so it stays unsized; the cap shows
  // up in the min-width below (48 chars * 8 + 24 = 408).
  expect(cols[2].style.width).toBe("");
  expect((root.querySelector("[data-role=rows]") as HTMLElement).style.minWidth).toBe("548px");   // 44 + 48 + 408 + 48
});

test("a table wider than two columns scrolls sideways instead of widening the page", () => {
  const wide = setup();
  wide.s.tables(new ReviewState([shares]));
  const wideTable = wide.root.querySelector("[data-role=rows]") as HTMLElement;
  const wideCols = Array.prototype.slice.call(wide.root.querySelectorAll("[data-role=rows] colgroup col")) as HTMLElement[];
  // Date is fixed at the date part (104), not the 176 its "2024-01-01 09:00:00"
  // would otherwise ask for; the other three are chars * 8 + 24 on the longer
  // of the header and the widest cell: "Shared content" 14, Link 11, Method 6.
  expect(wideCols[1].style.width).toBe("104px");
  // 44 (checkbox) + 104 + 136 + 112 + 72. Without the date rule this would be
  // 540, and the extra 72px would come off the column being read.
  expect(wideTable.style.minWidth).toBe("468px");
  expect((wideTable.parentElement as HTMLElement).className).toContain("overflow-x-auto");

  const narrow = setup();
  narrow.s.tables(new ReviewState([watchHistory(2)]));
  expect((narrow.root.querySelector("[data-role=rows]") as HTMLElement).style.minWidth).toBe("");
});

test("every paging button names itself", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(60)]));
  const names = ["first-page", "prev-page", "next-page", "last-page"].map((a) => {
    const b = root.querySelector("[data-action=" + a + "]") as HTMLElement;
    return b.getAttribute("aria-label");
  });
  expect(names).toEqual(["First page", "Previous page", "Next page", "Last page"]);
  for (const name of names) expect(name).toBeTruthy();
});

test("the share-all note appears only when there is more than one table", () => {
  const one = setup();
  one.s.tables(new ReviewState([watchHistory(2)]));
  expect(one.root.textContent).not.toContain("Sharing covers all");

  const many = setup();
  many.s.tables(new ReviewState([watchHistory(2), searches]));
  expect(many.root.textContent).toContain("Sharing covers all 2 tables, also the ones you have not opened.");
  expect(many.root.textContent).toContain("Checked everything? Press \"Show summary before sharing\" to continue.");
});

test("the confirm screen speaks of sharing throughout, and every button names its verb", () => {
  const { root, s } = setup();
  s.confirm(new ReviewState([searches]));
  expect(root.textContent).toContain("Ready to share?");
  expect(root.textContent).toContain("If you say no, only your decision is recorded.");
  expect(root.textContent).toContain("Do you want to share the above data?");
  expect((root.querySelector("[data-action=donate]") as HTMLElement).textContent).toBe("Yes, share for research");
  // The desktop's bare "No" sits beside its Yes in one flex row; these three
  // buttons wrap, so the decline has to carry its own verb.
  expect((root.querySelector("[data-action=decline]") as HTMLElement).textContent).toBe("No, do not share");
  expect((root.querySelector("[data-action=back]") as HTMLElement).textContent).toBe("Back");
  // No screen names a button "Donate" any more.
  expect(root.textContent).not.toContain("donate");
});

test("the Dutch screens read formally and speak of sharing", () => {
  const { root, s } = setup("nl");
  const state = new ReviewState([{ id: "tiktok_watch_history", columns: ["Date", "Link"], rows: [["2024-01-01", "https://x/a"]] }, searches]);
  s.tables(state);
  expect(root.textContent).toContain("Uw TikTok-gegevens");
  expect(root.textContent).toContain("Uw gegevens zijn verdeeld over 2 tabellen");
  expect(root.textContent).toContain("Toon samenvatting voor delen");
  s.confirm(state);
  expect(root.textContent).toContain("Klaar om te delen?");
  expect(root.textContent).toContain("Als u nee zegt, wordt alleen uw beslissing vastgelegd.");
  expect(root.textContent).toContain("Nee, niet delen");
  s.intro();
  expect(root.textContent).toContain("Doneer uw TikTok-gegevens");
});
