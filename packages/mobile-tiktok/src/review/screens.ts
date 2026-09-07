import { ReviewState, TableState } from "./state";
import { TABLES, text } from "../config";
import { t, formatCount, Locale } from "../text";

export type ErrorKind = "extract_failed" | "unexpected";
export type RetryKind = "too_large" | "not_tiktok" | "unreadable";

export interface ScreenHandlers {
  onFile(file: File): void;
  onSelectTable(i: number): void;
  onQuery(i: number, q: string): void;
  onDeleteMatches(i: number): void;
  onToggleSelect(i: number, row: number): void;
  onDeleteSelected(i: number): void;
  onPage(i: number, page: number): void;
  onJumpToMonth(i: number, month: string): void;
  onUndo(): void;
  onProceed(): void;
  onBack(): void;
  onRestart(): void;
  onDonate(): void;
  onDecline(): void;
  onRetryDonate(): void;
  onStop(): void;
  onReport(): void;
  onSkipReport(): void;
}

// The desktop data collector's two button shapes: auto width, its padding,
// rounded, Nunito button size from the shared preset.
const PRIMARY = "inline-block bg-primary text-white pt-15px pb-15px";
const SECONDARY = "inline-block bg-white text-primary border-2 border-primary pt-13px pb-13px";
const BUTTON = " pl-4 pr-4 font-button text-button rounded cursor-pointer touchstart-sensitive";
const SELECT = "mt-select block w-full border border-grey4 rounded px-3 py-2 font-body text-bodymedium bg-white";

function el(tag: string, className: string, textContent?: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  if (textContent !== undefined) e.textContent = textContent;
  return e;
}

function button(label: string, action: string, primary: boolean, onClick: () => void): HTMLElement {
  const b = el("button", (primary ? PRIMARY : SECONDARY) + BUTTON + " mt-3 mr-2", label);
  b.setAttribute("data-action", action);
  b.addEventListener("click", onClick);
  b.addEventListener("touchstart", () => undefined);   // enables :active styling on iOS
  return b;
}

export class Screens {
  private root: HTMLElement;
  private locale: Locale;
  private h: ScreenHandlers;
  private afterRender: () => void;
  private tablesIndex: number | null = null;
  private tableSelectEl: HTMLSelectElement | null = null;
  private searchEl: HTMLInputElement | null = null;
  private counterEl: HTMLElement | null = null;
  private controlsEl: HTMLElement | null = null;
  private pageBars: HTMLElement[] = [];
  private monthSelectEl: HTMLSelectElement | null = null;
  private rowsEl: HTMLElement | null = null;
  private nextTableLineEl: HTMLElement | null = null;
  private renderedPage = -1;
  private renderedRows: number[] | null = null;
  private expanded: { [row: number]: boolean } = {};

  constructor(root: HTMLElement, locale: Locale, handlers: ScreenHandlers, afterRender: () => void) {
    this.root = root;
    this.locale = locale;
    this.h = handlers;
    this.afterRender = afterRender;
  }

  private tx(key: string, vars?: { [k: string]: string | number }): string { return t(key, this.locale, vars); }

  private page(title: string, body?: string): HTMLElement {
    this.tablesIndex = null;
    this.tableSelectEl = null;
    this.searchEl = null;
    this.counterEl = null;
    this.controlsEl = null;
    this.pageBars = [];
    this.monthSelectEl = null;
    this.rowsEl = null;
    this.nextTableLineEl = null;
    this.renderedPage = -1;
    this.renderedRows = null;
    this.expanded = {};
    this.root.innerHTML = "";
    const page = el("div", "px-6 py-6 max-w-3xl mx-auto");
    page.appendChild(el("h1", "font-title3 text-title3 font-bold mb-3", title));
    if (body) page.appendChild(el("p", "font-body text-bodymedium text-grey1 mb-4", body));
    this.root.appendChild(page);
    return page;
  }

  private finish(): void { this.afterRender(); }

  private fileInput(page: HTMLElement, label: string): void {
    const wrap = el("label", "block");
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip,application/zip";
    input.className = "mt-visually-hidden";
    input.addEventListener("change", () => { const f = input.files && input.files[0]; if (f) this.h.onFile(f); });
    const fake = el("span", PRIMARY + BUTTON + " mt-3", label);
    wrap.appendChild(input);
    wrap.appendChild(fake);
    page.appendChild(wrap);
  }

  intro(): void {
    const page = this.page(this.tx("intro_title"), this.tx("intro_body"));
    this.fileInput(page, this.tx("choose_file"));
    this.finish();
  }

  working(): void {
    const page = this.page(this.tx("working"));
    const spin = el("div", "mt-spinner mx-auto my-8");
    page.appendChild(spin);
    this.finish();
  }

  retry(kind: RetryKind): void {
    const page = this.page(this.tx("error_title"), this.tx("retry_" + kind));
    this.fileInput(page, this.tx("try_again"));
    page.appendChild(button(this.tx("stop"), "stop", false, () => this.h.onStop()));
    this.finish();
  }

  private tableTitle(ts: TableState): string {
    const c = TABLES.filter((x) => x.id === ts.table.id)[0];
    return c ? text(c.title, this.locale) : ts.table.id;
  }

  private buildTableSelect(state: ReviewState): HTMLSelectElement {
    const sel = document.createElement("select");
    sel.className = SELECT + " mb-3";
    sel.setAttribute("data-role", "table-select");
    state.tables.forEach((other, j) => {
      const opt = document.createElement("option");
      opt.value = String(j);
      opt.textContent = this.tableTitle(other) + " (" + formatCount(state.keptCount(j), this.locale) + ")";
      sel.appendChild(opt);
    });
    sel.value = String(state.activeIndex);
    sel.addEventListener("change", () => this.h.onSelectTable(Number(sel.value)));
    return sel;
  }

  private updateTableSelect(state: ReviewState): void {
    const sel = this.tableSelectEl;
    if (!sel) return;
    state.tables.forEach((other, j) => {
      const opt = sel.options[j];
      if (opt) opt.textContent = this.tableTitle(other) + " (" + formatCount(state.keptCount(j), this.locale) + ")";
    });
    sel.value = String(state.activeIndex);
  }

  private updateCounter(i: number, ts: TableState, state: ReviewState): void {
    if (this.counterEl) this.counterEl.textContent = this.tx("rows_kept", { kept: state.keptCount(i), deleted: ts.deletedCount });
  }

  // The controls line is small enough to rebuild wholesale, which keeps the
  // buttons in a fixed order however the counts change under them.
  private updateControls(i: number, ts: TableState, state: ReviewState, visible: number[]): void {
    const line = this.controlsEl;
    if (!line) return;
    line.innerHTML = "";
    const selected = state.selectedCount(i);
    if (selected > 0) {
      const b = el("button", SECONDARY + BUTTON + " mr-2 mb-2", this.tx("remove_selected", { n: selected }));
      b.setAttribute("data-action", "remove-selected");
      // No confirm dialog: the participant ticked these rows one by one, and
      // Undo brings the whole batch back.
      b.addEventListener("click", () => this.h.onDeleteSelected(i));
      b.addEventListener("touchstart", () => undefined);
      line.appendChild(b);
    }
    if (ts.matches !== null && visible.length > 0) {
      const n = visible.length;
      const b = el("button", SECONDARY + BUTTON + " mr-2 mb-2", this.tx("remove_matches", { n }));
      b.setAttribute("data-action", "remove-matches");
      b.addEventListener("click", () => { if (window.confirm(this.tx("confirm_remove", { n }))) this.h.onDeleteMatches(i); });
      b.addEventListener("touchstart", () => undefined);
      line.appendChild(b);
    }
    if (state.canUndo()) {
      const u = el("button", "font-label text-label text-primary cursor-pointer mr-2 mb-2", this.tx("undo"));
      u.setAttribute("data-action", "undo");
      u.addEventListener("click", () => this.h.onUndo());
      line.appendChild(u);
    }
  }

  private buildPageBar(i: number, state: ReviewState): HTMLElement {
    const bar = el("div", "mb-2");
    bar.setAttribute("data-role", "page-bar");
    const prev = el("button", SECONDARY + BUTTON + " mr-2", this.tx("prev_page"));
    prev.setAttribute("data-action", "prev-page");
    prev.addEventListener("click", () => this.h.onPage(i, state.tables[i].page - 1));
    const next = el("button", SECONDARY + BUTTON + " mr-2", this.tx("next_page"));
    next.setAttribute("data-action", "next-page");
    next.addEventListener("click", () => this.h.onPage(i, state.tables[i].page + 1));
    const label = el("span", "font-body text-bodysmall text-grey2");
    label.setAttribute("data-role", "page-label");
    bar.appendChild(prev);
    bar.appendChild(next);
    bar.appendChild(label);
    return bar;
  }

  private updatePageBars(i: number, state: ReviewState): void {
    const page = state.tables[i].page;
    const count = state.pageCount(i);
    for (const bar of this.pageBars) {
      // One page: nothing to page between, so the controls stay out of the way.
      bar.style.display = count === 1 ? "none" : "";
      const prev = bar.querySelector("[data-action=prev-page]") as HTMLButtonElement | null;
      const next = bar.querySelector("[data-action=next-page]") as HTMLButtonElement | null;
      const label = bar.querySelector("[data-role=page-label]") as HTMLElement | null;
      if (prev) { prev.disabled = page === 0; prev.style.opacity = page === 0 ? "0.4" : ""; }
      if (next) { next.disabled = page >= count - 1; next.style.opacity = page >= count - 1 ? "0.4" : ""; }
      if (label) label.textContent = this.tx("page_label", { x: page + 1, y: count });
    }
  }

  // Next table steps to the table after this one; hidden past the last table,
  // where there is nothing left to step to. Rebuilt wholesale like the
  // controls line above, so its presence always matches the active table.
  private updateNextTableLine(i: number, state: ReviewState): void {
    const line = this.nextTableLineEl;
    if (!line) return;
    line.innerHTML = "";
    const hasNext = i < state.tables.length - 1;
    // No dead space below the page bar when there is nothing to show here.
    line.className = hasNext ? "mb-2" : "";
    if (hasNext) {
      const b = button(this.tx("next_table"), "next-table", false, () => this.h.onSelectTable(i + 1));
      line.appendChild(b);
    }
  }

  // The page scrolls in the host, not in the iframe, so window.scrollTo does
  // nothing here; scrollIntoView on an element inside the frame scrolls the
  // ancestor document instead, at least in WebKit (device checklist item to
  // confirm). Wrapped defensively: a Safari 12 corner case throwing here must
  // not take the render down with it.
  private scrollTableTop(): void {
    if (!this.tableSelectEl) return;
    try {
      this.tableSelectEl.scrollIntoView();
    } catch (_) {
      // deliberately swallowed
    }
  }

  private buildMonthSelect(i: number): HTMLSelectElement {
    const sel = document.createElement("select");
    sel.className = SELECT + " mb-2";
    sel.setAttribute("data-role", "month-select");
    sel.addEventListener("change", () => {
      const month = sel.value;
      sel.value = "";
      if (month !== "") this.h.onJumpToMonth(i, month);
    });
    return sel;
  }

  private updateMonthSelect(months: string[]): void {
    const sel = this.monthSelectEl;
    if (!sel) return;
    sel.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = this.tx("jump_month");
    sel.appendChild(placeholder);
    for (const month of months) {
      const opt = document.createElement("option");
      opt.value = month;
      opt.textContent = month;
      sel.appendChild(opt);
    }
    sel.value = "";
  }

  private buildRow(i: number, rowIndex: number, cells: string[], selected: boolean): HTMLElement {
    const row = el("div", "mt-row flex flex-row items-start border-b border-grey4 py-2");
    row.setAttribute("data-row", String(rowIndex));
    if (this.expanded[rowIndex]) row.setAttribute("data-expanded", "true");

    const check = el("label", "mt-check flex flex-row items-center justify-center mr-2");
    const box = document.createElement("input");
    box.type = "checkbox";
    // iOS 12 draws a native checkbox as a small grey square with almost no
    // visual weight. The input stays in the DOM, focusable and the target of
    // the label's tap, but visually hidden; .mt-box draws the state instead.
    box.className = "mt-visually-hidden";
    box.setAttribute("data-role", "select");
    // Read out by VoiceOver in place of an unlabelled tick box. Local to this
    // frame: nothing derived from the archive is ever sent anywhere.
    box.setAttribute("aria-label", cells[0]);
    box.checked = selected;
    box.addEventListener("change", () => this.h.onToggleSelect(i, rowIndex));
    check.appendChild(box);
    // Sizing, checked-fill and the tick live in .mt-box; the border and its
    // rounding are Tailwind's own utilities, matching the button borders
    // elsewhere on this page instead of a duplicated hex.
    check.appendChild(el("span", "mt-box border-2 border-primary rounded"));
    row.appendChild(check);

    const body = el("div", "mt-rowbody flex-grow");
    body.setAttribute("data-role", "cells");
    for (let c = 0; c < cells.length; c++) {
      body.appendChild(el("div", c === 0 ? "mt-cell font-body text-bodymedium font-bold" : "mt-cell font-body text-bodysmall text-grey2", cells[c]));
    }
    // Cells are one truncated line each until the participant taps them; then
    // the row wraps so a long link can be read in full.
    body.addEventListener("click", () => {
      if (row.getAttribute("data-expanded")) { row.removeAttribute("data-expanded"); this.expanded[rowIndex] = false; }
      else { row.setAttribute("data-expanded", "true"); this.expanded[rowIndex] = true; }
      // The row just grew or shrank: the host sizes the iframe from our height,
      // so an expanded row would otherwise be cut off at the bottom.
      this.afterRender();
    });
    row.appendChild(body);
    return row;
  }

  private static sameRows(a: number[] | null, b: number[]): boolean {
    if (a === null || a.length !== b.length) return false;
    for (let k = 0; k < a.length; k++) if (a[k] !== b[k]) return false;
    return true;
  }

  private renderRows(i: number, ts: TableState, state: ReviewState): void {
    const host = this.rowsEl;
    if (!host) return;
    const page = state.tables[i].page;
    const indices = state.pageRows(i);

    // The same rows are still on screen, so only the ticks can have moved.
    // Rebuilding fifty nodes here would pull the tapped checkbox out from under
    // the finger and close any row the participant had opened to read.
    if (page === this.renderedPage && Screens.sameRows(this.renderedRows, indices)) {
      const boxes = host.querySelectorAll("input[data-role=select]");
      for (let k = 0; k < indices.length && k < boxes.length; k++) {
        (boxes[k] as HTMLInputElement).checked = state.isSelected(i, indices[k]);
      }
      return;
    }

    if (page !== this.renderedPage) { this.expanded = {}; this.renderedPage = page; }
    host.innerHTML = "";
    this.renderedRows = indices;
    if (indices.length === 0) {
      host.appendChild(el("p", "font-body text-bodysmall text-grey2 py-4", this.tx("no_rows")));
      return;
    }
    const rows = ts.table.rows;
    for (const r of indices) host.appendChild(this.buildRow(i, r, rows[r], state.isSelected(i, r)));
  }

  // scrollTop is set by the controller for a table switch (dropdown or Next
  // table) and a page change; not for a checkbox toggle, a search keystroke,
  // or anything else that re-renders this screen in place.
  tables(state: ReviewState, scrollTop = false): void {
    const i = state.activeIndex;
    const ts = state.tables[i];
    const visible = state.visibleRows(i);

    // Same table, search box still on screen: update in place so typing does
    // not get its input element (and keyboard focus) replaced out from under it.
    if (this.tablesIndex === i && this.searchEl && document.contains(this.searchEl)) {
      this.updateTableSelect(state);
      this.updateCounter(i, ts, state);
      this.updateControls(i, ts, state, visible);
      this.updatePageBars(i, state);
      if (this.monthSelectEl) this.updateMonthSelect(state.months(i));
      this.updateNextTableLine(i, state);
      this.renderRows(i, ts, state);
      this.finish();
      if (scrollTop) this.scrollTableTop();
      return;
    }

    const page = this.page(this.tx("tables_title"), this.tx("tables_body"));
    const cfg = TABLES.filter((c) => c.id === ts.table.id)[0];

    const tableSelect = this.buildTableSelect(state);
    page.appendChild(tableSelect);

    if (cfg) page.appendChild(el("p", "font-body text-bodysmall text-grey2 mb-2", text(cfg.description, this.locale)));

    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = this.tx("search");
    search.value = ts.query;
    search.className = "w-full border border-grey4 rounded px-3 py-2 mb-2 font-body text-bodymedium";
    let timer = 0;
    search.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => this.h.onQuery(i, search.value), 150);
      if (search.value.length <= 2) { window.clearTimeout(timer); this.h.onQuery(i, search.value); }
    });
    page.appendChild(search);

    const counterLine = el("div", "mb-2");
    const counter = el("span", "font-body text-bodysmall text-grey2");
    counterLine.appendChild(counter);
    page.appendChild(counterLine);

    const controls = el("div", "mb-2");
    page.appendChild(controls);

    // Gated on the table having dates at all, not on the current result set:
    // a search that matches nothing must not take the picker away for good.
    const monthSelect = ts.table.columns.indexOf("Date") >= 0 ? this.buildMonthSelect(i) : null;
    if (monthSelect) page.appendChild(monthSelect);

    const topBar = this.buildPageBar(i, state);
    page.appendChild(topBar);

    const rowsHost = el("div", "border-t border-grey4");
    rowsHost.setAttribute("data-role", "rows");
    page.appendChild(rowsHost);

    const bottomBar = this.buildPageBar(i, state);
    bottomBar.className = "mt-3 mb-2";
    page.appendChild(bottomBar);

    const nextTableLine = el("div", "mb-2");
    page.appendChild(nextTableLine);

    const nav = el("div", "");
    // Back re-rendered the same screen here, so it is Choose another file
    // instead: the tables screen has nothing behind it to go back to.
    nav.appendChild(button(this.tx("try_again"), "restart", false, () => this.h.onRestart()));
    nav.appendChild(button(this.tx("proceed"), "proceed", true, () => this.h.onProceed()));
    page.appendChild(nav);

    this.tablesIndex = i;
    this.tableSelectEl = tableSelect;
    this.searchEl = search;
    this.counterEl = counter;
    this.controlsEl = controls;
    this.pageBars = [topBar, bottomBar];
    this.monthSelectEl = monthSelect;
    this.rowsEl = rowsHost;
    this.nextTableLineEl = nextTableLine;
    this.renderedPage = state.tables[i].page;

    this.updateCounter(i, ts, state);
    this.updateControls(i, ts, state, visible);
    this.updatePageBars(i, state);
    if (monthSelect) this.updateMonthSelect(state.months(i));
    this.updateNextTableLine(i, state);
    this.renderRows(i, ts, state);

    this.finish();
    // The host resizes the iframe from the height reported above; measure once
    // more on the next tick so it also sees the page as laid out inside the
    // frame it just grew. The scroll (if asked for) waits for that tick too:
    // scrolling against the pre-resize layout would target the wrong offset
    // on a switch that grows or shrinks the frame.
    window.setTimeout(() => {
      this.afterRender();
      if (scrollTop) this.scrollTableTop();
    }, 0);
  }

  confirm(state: ReviewState): void {
    const page = this.page(this.tx("confirm_title"), this.tx("confirm_body"));
    const ul = el("ul", "mb-4");
    state.tables.forEach((ts, j) => {
      const c = TABLES.filter((x) => x.id === ts.table.id)[0];
      ul.appendChild(el("li", "font-body text-bodymedium py-1 border-b border-grey4",
        (c ? text(c.title, this.locale) : ts.table.id) + ": " + this.tx("rows_kept", { kept: state.keptCount(j), deleted: ts.deletedCount })));
    });
    page.appendChild(ul);
    page.appendChild(button(this.tx("donate"), "donate", true, () => this.h.onDonate()));
    page.appendChild(button(this.tx("decline"), "decline", false, () => this.h.onDecline()));
    page.appendChild(button(this.tx("back"), "back", false, () => this.h.onBack()));
    this.finish();
  }

  sending(): void {
    const page = this.page(this.tx("sending"));
    page.appendChild(el("div", "mt-spinner mx-auto my-8"));
    this.finish();
  }

  done(declined = false): void {
    this.page(this.tx("done_title"), this.tx(declined ? "declined_body" : "done_body"));
    this.finish();
  }

  failed(): void {
    const page = this.page(this.tx("failed_title"), this.tx("failed_body"));
    page.appendChild(button(this.tx("retry_send"), "retry-donate", true, () => this.h.onRetryDonate()));
    page.appendChild(button(this.tx("stop"), "stop", false, () => this.h.onStop()));
    this.finish();
  }

  error(_kind: ErrorKind): void {
    const page = this.page(this.tx("error_title"), this.tx("error_body"));
    page.appendChild(button(this.tx("report"), "report", true, () => this.h.onReport()));
    page.appendChild(button(this.tx("skip"), "skip", false, () => this.h.onSkipReport()));
    this.finish();
  }

  incomplete(): void {
    this.page(this.tx("incomplete_title"), this.tx("incomplete_body"));
    this.finish();
  }
}
