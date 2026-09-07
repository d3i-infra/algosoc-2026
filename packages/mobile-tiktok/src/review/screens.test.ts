import { Screens, ScreenHandlers } from "./screens";
import { ReviewState } from "./state";
import type { Table } from "../extract";

function handlers(): ScreenHandlers & { calls: string[] } {
  const calls: string[] = [];
  const h = {} as ScreenHandlers & { calls: string[] };
  h.calls = calls;
  for (const name of ["onFile", "onSelectTable", "onQuery", "onDeleteMatches", "onToggleSelect", "onDeleteSelected", "onPage", "onJumpToMonth", "onUndo", "onProceed", "onBack", "onRestart", "onDonate", "onDecline", "onRetryDonate", "onStop", "onReport", "onSkipReport"]) {
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
const hashtags: Table = { id: "tiktok_hashtag", columns: ["HashtagName", "HashtagLink"], rows: [["#a", "https://x/a"], ["#b", "https://x/b"]] };

function rowsIn(root: HTMLElement): HTMLElement[] {
  return Array.prototype.slice.call(root.querySelectorAll(".mt-row")) as HTMLElement[];
}

function pageLabel(root: HTMLElement): string {
  return (root.querySelector("[data-role=page-label]") as HTMLElement).textContent || "";
}

test("intro shows the file input and reports a chosen file", () => {
  const { root, h, s } = setup("nl");
  s.intro();
  expect(root.textContent).toContain("Doneer je TikTok-gegevens");
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
  expect(sel.options[0].textContent).toBe("Watch history (2)");
  expect(sel.options[1].textContent).toBe("Searches (1)");
  expect(sel.value).toBe("0");
  expect(root.querySelector("[data-tab]")).toBeNull();
  sel.value = "1";
  sel.dispatchEvent(new Event("change"));
  expect(h.calls).toContain("onSelectTable:1");
});

test("a large table's select option shows a locale-grouped kept count", () => {
  const { root, s } = setup("en");
  const state = new ReviewState([watchHistory(200000)]);
  s.tables(state);
  const sel = root.querySelector("select[data-role=table-select]") as HTMLSelectElement;
  expect(sel.options[0].textContent).toBe("Watch history (200,000)");
});

test("only the current page of rows is rendered, with the page label and paging handlers", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(52)]);
  s.tables(state);
  expect(rowsIn(root).length).toBe(50);
  expect(rowsIn(root)[0].getAttribute("data-row")).toBe("0");
  expect(pageLabel(root)).toBe("Page 1 of 2");
  (root.querySelector("[data-action=next-page]") as HTMLElement).click();
  expect(h.calls).toContain("onPage:0,1");
  state.setPage(0, 1);
  s.tables(state);
  expect(rowsIn(root).length).toBe(2);
  expect(rowsIn(root)[0].getAttribute("data-row")).toBe("50");
  expect(pageLabel(root)).toBe("Page 2 of 2");
  (root.querySelector("[data-action=prev-page]") as HTMLElement).click();
  expect(h.calls).toContain("onPage:0,0");
});

test("the prev and next group is repeated below the rows", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(52)]));
  expect(root.querySelectorAll("[data-action=prev-page]").length).toBe(2);
  expect(root.querySelectorAll("[data-action=next-page]").length).toBe(2);
  expect(root.querySelectorAll("[data-role=page-label]").length).toBe(2);
  const bars = Array.prototype.slice.call(root.querySelectorAll("[data-role=page-bar]")) as HTMLElement[];
  expect(bars.length).toBe(2);
  expect(bars.map((b) => b.style.display)).toEqual(["", ""]);
});

test("the page bars are out of the way when everything fits on one page", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(6)]);
  s.tables(state);
  const bars = Array.prototype.slice.call(root.querySelectorAll("[data-role=page-bar]")) as HTMLElement[];
  expect(bars.map((b) => b.style.display)).toEqual(["none", "none"]);
  expect(pageLabel(root)).toBe("Page 1 of 1");
  // The month picker is not part of that group, so it stays reachable.
  expect((root.querySelector("[data-role=month-select]") as HTMLElement).parentElement!.getAttribute("data-role")).not.toBe("page-bar");
});

test("a checkbox tap leaves the row nodes and any expansion in place", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(52)]);
  s.tables(state);
  const firstRow = rowsIn(root)[0];
  (firstRow.querySelector("[data-role=cells]") as HTMLElement).click();
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
  (rowsIn(root)[0].querySelector("[data-role=cells]") as HTMLElement).click();
  expect(renders()).toBe(before + 1);
  (rowsIn(root)[0].querySelector("[data-role=cells]") as HTMLElement).click();
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
  expect(btn.textContent).toBe("Remove selected (2)");
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
  const cells = row.querySelector("[data-role=cells]") as HTMLElement;
  expect(row.hasAttribute("data-expanded")).toBe(false);
  cells.click();
  expect(row.getAttribute("data-expanded")).toBe("true");
  cells.click();
  expect(row.hasAttribute("data-expanded")).toBe(false);
});

test("every cell of the row is rendered, first one bold", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([{ id: "tiktok_share_history", columns: ["Date", "SharedContent", "Link", "Method"], rows: [["2024-01-01", "video", "https://x/1", "Copy"]] }]));
  const cells = rowsIn(root)[0].querySelectorAll(".mt-cell");
  expect(cells.length).toBe(4);
  expect(cells[0].className).toContain("font-bold");
  expect(cells[0].textContent).toBe("2024-01-01");
  expect(cells[2].textContent).toBe("https://x/1");
});

test("a month select is offered for a dated table and jumps on change", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(52)]);
  s.tables(state);
  const months = root.querySelector("select[data-role=month-select]") as HTMLSelectElement;
  expect(months).not.toBeNull();
  const values = Array.prototype.slice.call(months.options).map((o: HTMLOptionElement) => o.value);
  expect(values).toEqual(["", "2024-01", "2024-02"]);
  expect(months.options[0].textContent).toBe("Jump to month");
  months.value = "2024-02";
  months.dispatchEvent(new Event("change"));
  expect(h.calls).toContain("onJumpToMonth:0,2024-02");
});

test("no month select for a table without a Date column", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([hashtags]));
  expect(root.querySelector("select[data-role=month-select]")).toBeNull();
  expect(root.querySelector("select[data-role=table-select]")).not.toBeNull();
});

test("a dated table keeps its month select even when the search matches nothing", () => {
  const { root, s } = setup();
  const state = new ReviewState([watchHistory(52)]);
  state.setQuery(0, "nothing-matches-this");
  s.tables(state);
  const months = root.querySelector("select[data-role=month-select]") as HTMLSelectElement;
  expect(months).not.toBeNull();
  expect(months.options.length).toBe(1);
  state.setQuery(0, "");
  s.tables(state);
  expect(root.querySelector("select[data-role=month-select]")).toBe(months);
  expect(months.options.length).toBe(3);
});

test("remove-all button only with an active query", () => {
  const { root, s } = setup();
  const state = new ReviewState([searches]);
  s.tables(state);
  expect(root.querySelector("[data-action=remove-matches]")).toBeNull();
  state.setQuery(0, "q");
  s.tables(state);
  expect(root.querySelector("[data-action=remove-matches]")).not.toBeNull();
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
  expect(root.querySelector("[data-action=remove-matches]")).not.toBeNull();
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
  state.setPage(0, 1);
  s.tables(state);
  expect(root.querySelector("input[type=search]")).toBe(search);
  expect(root.querySelector("select[data-role=table-select]")).toBe(sel);
  expect(rowsIn(root).length).toBe(2);
  expect(pageLabel(root)).toBe("Page 2 of 2");
  state.toggleSelected(0, 50);
  state.deleteSelected(0);
  s.tables(state);
  expect(sel.options[0].textContent).toBe("Watch history (51)");
  expect(root.textContent).toContain("51 rows, 1 removed");
  expect(pageLabel(root)).toBe("Page 2 of 2");
  expect(root.querySelector("[data-action=undo]")).not.toBeNull();
});

test("an emptied table shows the no-rows line", () => {
  const { root, s } = setup();
  const state = new ReviewState([searches]);
  s.tables(state);
  state.setQuery(0, "nothing-matches-this");
  s.tables(state);
  expect(rowsIn(root).length).toBe(0);
  expect(root.textContent).toContain("No rows to show.");
  expect(pageLabel(root)).toBe("Page 1 of 1");
});

test("the review screen scrolls as one page: no inner scroll container", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(52)]));
  // The windowed list gave its container a measured pixel height and an
  // absolutely positioned spacer; the page now flows on its own.
  const sized = (Array.prototype.slice.call(root.querySelectorAll("div")) as HTMLElement[])
    .filter((d) => d.style.height !== "" || d.style.overflowY !== "");
  expect(sized).toEqual([]);
  const rowsHost = root.querySelector("[data-role=rows]") as HTMLElement;
  expect(rowsHost.parentElement).toBe(root.firstChild);
});

test("buttons keep the desktop look and are not full width", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const proceed = root.querySelector("[data-action=proceed]") as HTMLElement;
  expect(proceed.className).toContain("inline-block");
  expect(proceed.className).toContain("bg-primary");
  expect(proceed.className).toContain("font-button");
  expect(proceed.className).not.toContain("w-full");
  const restart = root.querySelector("[data-action=restart]") as HTMLElement;
  expect(restart.className).toContain("border-2");
  expect(restart.className).toContain("border-primary");
  expect(restart.className).toContain("text-primary");
  expect(restart.className).not.toContain("w-full");
});

test("Next table steps to the next table and is absent on the last one", () => {
  const { root, h, s } = setup();
  const state = new ReviewState([watchHistory(2), searches]);
  s.tables(state);
  const next = root.querySelector("[data-action=next-table]") as HTMLElement;
  expect(next).not.toBeNull();
  expect(next.textContent).toBe("Next table");
  next.click();
  expect(h.calls).toContain("onSelectTable:1");

  state.activeIndex = 1;
  s.tables(state);
  expect(root.querySelector("[data-action=next-table]")).toBeNull();
});

test("the tables screen primary button reads To donation summary", () => {
  const { root, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  const proceed = root.querySelector("[data-action=proceed]") as HTMLElement;
  expect(proceed.textContent).toBe("To donation summary");
});

const tick = () => new Promise((r) => setTimeout(r, 0));

test("the table select scrolls into view after a table switch or a page change, not after a toggle or a search keystroke", async () => {
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
    expect(calls[0]).toBe(root.querySelector("[data-role=table-select]"));

    // A checkbox toggle re-renders in place too, but is not a scroll trigger.
    state.toggleSelected(0, 50);
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

test("the tables screen offers Choose another file instead of Back", () => {
  const { root, h, s } = setup();
  s.tables(new ReviewState([watchHistory(2)]));
  expect(root.querySelector("[data-action=back]")).toBeNull();
  const restart = root.querySelector("[data-action=restart]") as HTMLElement;
  expect(restart.textContent).toBe("Choose another file");
  restart.click();
  expect(h.calls).toContain("onRestart:");
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
