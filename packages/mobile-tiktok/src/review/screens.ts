import { ReviewState, TableState } from "./state";
import { TABLES, text } from "../config";
import type { TableConfig } from "../config";
import { t, formatCount, Locale } from "../text";

export type ErrorKind = "extract_failed" | "unexpected";
export type RetryKind = "too_large" | "not_tiktok" | "unreadable";

export interface ScreenHandlers {
  onFile(file: File): void;
  onSelectTable(i: number): void;
  onQuery(i: number, q: string): void;
  onToggleSelect(i: number, row: number): void;
  onToggleSelectAll(i: number): void;
  onDeleteSelected(i: number): void;
  onPage(i: number, page: number): void;
  onUndo(i: number): void;
  onProceed(): void;
  onBack(): void;
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
// The desktop's table_selector.tsx search-box-shaped select, and its search
// bar (search_bar.tsx), class for class.
const SELECT = "mt-select w-full appearance-none text-grey1 font-body bg-white pl-3 pr-10 h-44px border-2 border-solid border-grey3 rounded-lg focus:outline-none focus:border-primary";
const SEARCH = "text-grey1 font-body pl-3 pr-3 w-full border-2 border-solid border-grey3 focus:outline-none focus:border-primary rounded-lg h-44px";
// table.tsx's StepButton, and the cell shape both its header and its body use.
const STEP = "flex items-center justify-center w-10 h-10 rounded-lg border-2 border-solid border-grey3 text-primary";
const CELL = "min-h-[2.1rem] px-3 flex items-center font-table-row";
// The desktop wraps its table in text-sm md:text-base, so at phone width the
// rows are 14px. CHAR_PX below is calibrated for that size, not the 16px the
// rest of the page inherits.
const TABLE = "table-fixed w-full text-sm";
// The checkbox column. The desktop's table.tsx says 32; here the column holds
// a 44px touch target (.mt-check), and a <col> narrower than its content only
// puts the markup at odds with what the browser draws.
const CHECKBOX_COLUMN_PX = 44;
// Inputs for the column widths below, the desktop's table.tsx rules at this
// package's font size. Character counts stand in for rendered width, which is
// accurate enough to divide a table up and needs no measurement - Safari 12
// has no ResizeObserver, so measuring would mean re-laying-out by hand.
const WIDTH_SAMPLE_ROWS = 50;    // representative, and cheap on a 65k-row table
const MIN_CHARS = 3;             // a column of one-character values stays tappable
const MAX_CHARS = 48;            // past this a column stops asking for more
const CHAR_PX = 8;               // Nunito Sans at text-sm (see TABLE above)
const CELL_PADDING_PX = 24;      // px-3 either side of a cell
// A timestamp is the one value whose full width can be bought back: it breaks
// at its own space, so the column is sized for the date and the time drops to
// a second line. Sizing it for all 19 characters instead left the column the
// participant actually reads (the link, the search term, the comment) about
// four characters wide on a 375px screen. The raw config column name is the
// test, not the translated header, so it holds in both locales.
const DATE_COLUMN = "Date";
const DATE_CHARS = 10;           // "2024-12-03"

function el(tag: string, className: string, textContent?: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  if (textContent !== undefined) e.textContent = textContent;
  return e;
}

// The desktop's icons are React elements and imported SVG files; the same
// shapes are built here through the DOM. innerHTML would be shorter, but the
// CSP the host serves this frame under is not ours to assume.
const SVG_NS = "http://www.w3.org/2000/svg";
type Attrs = { [name: string]: string };

function svgNode(tag: string, attrs: Attrs): SVGElement {
  const e = document.createElementNS(SVG_NS, tag);
  for (const name in attrs) e.setAttribute(name, attrs[name]);
  return e;
}

function svgIcon(className: string, viewBox: string, own: Attrs, children: Array<[string, Attrs]>): SVGElement {
  const root = svgNode("svg", { "class": className, viewBox: viewBox, fill: "none", "aria-hidden": "true" });
  for (const name in own) root.setAttribute(name, own[name]);
  for (const child of children) root.appendChild(svgNode(child[0], child[1]));
  return root;
}

// Every stroked icon below is drawn the way the desktop draws them: 2px round
// strokes in the current text colour, so one Tailwind text-* class colours it.
const STROKED: Attrs = { stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" };

function strokeIcon(className: string, viewBox: string, ds: string[]): SVGElement {
  const children: Array<[string, Attrs]> = [];
  for (const d of ds) children.push(["path", { d: d }]);
  return svgIcon(className, viewBox, STROKED, children);
}

// table_selector.tsx
function stackIcon(className: string): SVGElement {
  return strokeIcon(className, "0 0 24 24", ["M12 3 3 7.5l9 4.5 9-4.5L12 3Z", "m3 12 9 4.5 9-4.5", "m3 16.5 9 4.5 9-4.5"]);
}
function chevronLeftIcon(className: string): SVGElement { return strokeIcon(className, "0 0 24 24", ["m15 6-6 6 6 6"]); }
function chevronRightIcon(className: string): SVGElement { return strokeIcon(className, "0 0 24 24", ["m9 6 6 6-6 6"]); }

// pagination.tsx
function backwardIcon(className: string): SVGElement { return strokeIcon(className, "0 0 6 10", ["M5 1 1 5l4 4"]); }
function forwardIcon(className: string): SVGElement { return strokeIcon(className, "0 0 6 10", ["m1 9 4-4-4-4"]); }
function doubleBackwardIcon(className: string): SVGElement { return strokeIcon(className, "0 0 12 10", ["M5 1 1 5l4 4m6-8L7 5l4 4"]); }
function doubleForwardIcon(className: string): SVGElement { return strokeIcon(className, "0 0 12 10", ["m7 9 4-4-4-4M1 9l4-4-4-4"]); }

// table_items.tsx. The desktop fills the bars with the primary hex directly;
// currentColor lets one text-primary carry it here.
function tableIcon(className: string): SVGElement {
  const bars = [[9, 9], [9, 13], [9, 17], [15, 9], [15, 13], [15, 17]];
  const children: Array<[string, Attrs]> = [];
  for (const bar of bars) {
    children.push(["rect", { x: String(bar[0]), y: String(bar[1]), width: "4", height: "2", fill: "currentColor" }]);
  }
  children.push(["rect", { x: "4", y: "4", width: "15", height: "3", fill: "currentColor" }]);
  children.push(["rect", { x: "4", y: "9", width: "3", height: "10", fill: "currentColor" }]);
  return svgIcon(className, "4 4 18 18", {}, children);
}

// assets/images/undo.svg
function undoIcon(className: string): SVGElement {
  return svgIcon(className, "0 0 24 24", { stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" }, [
    ["path", { d: "M4 21H14.087C17.7826 21 21 18.375 21 14C21 9.625 17.7826 7 14.087 7H7.69565" }],
    ["path", { d: "M10 3L6 7L10 11" }],
  ]);
}

// assets/images/delete.svg. The exported file draws the lid and the handle as
// masked rects to fake an inner stroke; the same outlines are stroked plainly
// here, which Safari 12 renders identically at 24px and needs no document-wide
// mask ids.
function deleteIcon(className: string): SVGElement {
  return svgIcon(className, "0 0 24 24", { stroke: "currentColor", "stroke-width": "2", "stroke-linejoin": "round" }, [
    ["path", { d: "M5.5 7L6.5 21H17.5L18.5 7" }],
    ["rect", { x: "3", y: "4", width: "18", height: "3", rx: "1" }],
    ["path", { d: "M9 2C9 1.44772 9.44772 1 10 1H14C14.5523 1 15 1.44772 15 2V4H9V2Z" }],
  ]);
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
  private topEl: HTMLElement | null = null;
  private tableSelectEl: HTMLSelectElement | null = null;
  private positionEl: HTMLElement | null = null;
  private prevTableEl: HTMLButtonElement | null = null;
  private nextTableEl: HTMLButtonElement | null = null;
  private searchEl: HTMLInputElement | null = null;
  private summaryLineEl: HTMLElement | null = null;
  private selectAllEl: HTMLInputElement | null = null;
  private controlsEl: HTMLElement | null = null;
  private pageBars: HTMLElement[] = [];
  private rowsEl: HTMLElement | null = null;
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
    this.topEl = null;
    this.tableSelectEl = null;
    this.positionEl = null;
    this.prevTableEl = null;
    this.nextTableEl = null;
    this.searchEl = null;
    this.summaryLineEl = null;
    this.selectAllEl = null;
    this.controlsEl = null;
    this.pageBars = [];
    this.rowsEl = null;
    this.renderedPage = -1;
    this.renderedRows = null;
    this.expanded = {};
    this.root.innerHTML = "";
    // Narrow gutters on a 375px screen: every pixel taken here comes off the
    // table, which is the widest thing on the page.
    const page = el("div", "px-3 sm:px-6 py-6 max-w-3xl mx-auto");
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

  private optionLabel(state: ReviewState, j: number): string {
    const kept = state.keptCount(j);
    return this.tableTitle(state.tables[j]) + " (" + formatCount(kept, this.locale) + " " + this.tx(kept === 1 ? "row" : "rows") + ")";
  }

  // The desktop's table_selector.tsx: the participant sees one table at a
  // time, so this bar is the only place that says how many there are in total.
  // Left out entirely for a single table, where it would read "divided over 1
  // tables" and the option label would only repeat the title below it.
  private buildSelector(state: ReviewState): HTMLElement {
    const card = el("div", "flex flex-col p-3 bg-grey6 border-[0.2rem] border-grey4 rounded-lg mb-4");
    const total = state.tables.length;

    const intro = el("div", "flex mb-3");
    const icon = stackIcon("h-8 w-8 text-primary shrink-0 mr-3");
    intro.appendChild(icon);
    const copy = el("div", "flex flex-col");
    copy.appendChild(el("div", "text-title6 font-label", this.tx("selector_heading", { n: total })));
    copy.appendChild(el("p", "text-base font-body", this.tx("selector_explanation")));
    intro.appendChild(copy);
    card.appendChild(intro);

    const label = el("label", "block mb-3");
    label.appendChild(el("span", "text-title7 font-label block mb-1", this.tx("selector_label")));
    const sel = document.createElement("select");
    sel.className = SELECT;
    sel.setAttribute("data-role", "table-select");
    state.tables.forEach((_other, j) => {
      const opt = document.createElement("option");
      opt.value = String(j);
      opt.textContent = this.optionLabel(state, j);
      sel.appendChild(opt);
    });
    sel.value = String(state.activeIndex);
    sel.addEventListener("change", () => this.h.onSelectTable(Number(sel.value)));
    label.appendChild(sel);
    card.appendChild(label);

    const steps = el("div", "flex items-center");
    const prev = this.stepButton("prev-table", this.tx("prev_table"), chevronLeftIcon("h-5 w-5"), () => this.h.onSelectTable(state.activeIndex - 1));
    const position = el("span", "text-title7 font-label mx-3");
    position.setAttribute("data-role", "table-position");
    const next = this.stepButton("next-table", this.tx("next_table"), chevronRightIcon("h-5 w-5"), () => this.h.onSelectTable(state.activeIndex + 1));
    steps.appendChild(prev);
    steps.appendChild(position);
    steps.appendChild(next);
    card.appendChild(steps);

    this.tableSelectEl = sel;
    this.positionEl = position;
    this.prevTableEl = prev;
    this.nextTableEl = next;
    return card;
  }

  private stepButton(action: string, label: string, icon: SVGElement, onClick: () => void): HTMLButtonElement {
    const b = el("button", STEP) as HTMLButtonElement;
    b.setAttribute("data-action", action);
    b.setAttribute("aria-label", label);
    b.setAttribute("title", label);
    b.appendChild(icon);
    b.addEventListener("click", onClick);
    return b;
  }

  private updateSelector(state: ReviewState): void {
    const sel = this.tableSelectEl;
    if (!sel) return;
    state.tables.forEach((_other, j) => {
      const opt = sel.options[j];
      if (opt) opt.textContent = this.optionLabel(state, j);
    });
    sel.value = String(state.activeIndex);
    const i = state.activeIndex;
    const total = state.tables.length;
    // Positions, not counts: passed as strings so "1 of 12" never becomes
    // "1 of 12" grouped into something else in a locale that groups at 4.
    if (this.positionEl) this.positionEl.textContent = this.tx("selector_position", { i: String(i + 1), n: String(total) });
    Screens.setStepDisabled(this.prevTableEl, i === 0);
    Screens.setStepDisabled(this.nextTableEl, i >= total - 1);
  }

  private static setStepDisabled(b: HTMLButtonElement | null, disabled: boolean): void {
    if (!b) return;
    b.disabled = disabled;
    b.className = disabled ? STEP + " opacity-40" : STEP;
  }

  // table_items.tsx: the columns, the rows still in the table, and what has
  // been removed, with Undo sitting on the end of that sentence.
  private updateSummary(i: number, ts: TableState, state: ReviewState): void {
    const line = this.summaryLineEl;
    if (!line) return;
    line.innerHTML = "";
    line.appendChild(tableIcon("h-6 w-6 text-primary shrink-0 mr-1"));

    const kept = state.keptCount(i);
    const matched = state.visibleCount(i);
    const deleted = ts.deletedCount;
    let read: string;
    if (kept === 0) {
      read = this.tx("no_data");
    } else {
      const rows = ts.matches !== null && matched < kept
        ? formatCount(matched, this.locale) + " / " + formatCount(kept, this.locale) + " " + this.tx("rows")
        : formatCount(kept, this.locale) + " " + this.tx("rows");
      read = formatCount(ts.table.columns.length, this.locale) + " " + this.tx("columns") + ", " + rows;
    }

    const summary = el("span", "text-title7 font-label", read);
    summary.setAttribute("data-role", "summary");
    line.appendChild(summary);

    // The desktop greys the removed count away from the counts that describe
    // what is still there (table_items.tsx).
    if (deleted > 0) {
      const gone = el("span", "text-title7 font-label text-grey2", ", " + formatCount(deleted, this.locale) + " " + this.tx("deleted"));
      gone.setAttribute("data-role", "deleted");
      line.appendChild(gone);
    }

    // Undo speaks for this table's count beside it, so it appears only while
    // this table has something to undo (state keeps a stack per table).
    if (state.canUndo(i)) {
      // mt-check is the 44px touch target the tick boxes use; the icon stays
      // the desktop's 20px inside it.
      const u = el("button", "mt-check ml-1 text-primary shrink-0 flex items-center justify-center") as HTMLButtonElement;
      u.setAttribute("data-action", "undo");
      u.setAttribute("aria-label", this.tx("undo"));
      u.setAttribute("title", this.tx("undo"));
      u.appendChild(undoIcon("w-5 h-5"));
      u.addEventListener("click", () => this.h.onUndo(i));
      line.appendChild(u);
    }
  }

  // The footer's left half. Rebuilt wholesale, which is cheap and keeps the
  // button from lingering with a stale count when the selection empties.
  private updateControls(i: number, state: ReviewState): void {
    const line = this.controlsEl;
    if (!line) return;
    line.innerHTML = "";
    const selected = state.selectedCount(i);
    if (selected === 0) return;
    // The desktop's IconButton. No confirm dialog: the participant ticked
    // these rows one by one, and Undo brings the whole batch back.
    const b = el("button", "flex items-center cursor-pointer text-delete");
    b.setAttribute("data-action", "remove-selected");
    b.appendChild(deleteIcon("w-6 h-6 mr-2 shrink-0"));
    b.appendChild(el("span", "font-button text-buttonsmall", this.tx("delete", { n: selected })));
    b.addEventListener("click", () => this.h.onDeleteSelected(i));
    b.addEventListener("touchstart", () => undefined);
    line.appendChild(b);
  }

  // The desktop's pagination.tsx: chevrons either side of a plain "page of
  // pages" count, no words. Its outer pair steps ten pages at a time; here
  // they go to the first and the last page, because a page is 25 rows and a
  // watch history is hundreds of pages long.
  private buildPageBar(i: number, state: ReviewState): HTMLElement {
    const bar = el("div", "flex items-center p-3");
    bar.setAttribute("data-role", "page-bar");
    const page = (): number => state.tables[i].page;
    bar.appendChild(this.pageButton("first-page", "first_page", doubleBackwardIcon("h-4"), "mr-2", () => this.h.onPage(i, 0)));
    bar.appendChild(this.pageButton("prev-page", "prev_page", backwardIcon("h-4"), "mr-2", () => this.h.onPage(i, page() - 1)));
    const label = el("span", "text-center min-w-[3rem] font-title6 text-title6");
    label.setAttribute("data-role", "page-label");
    bar.appendChild(label);
    bar.appendChild(this.pageButton("next-page", "next_page", forwardIcon("h-4"), "ml-2", () => this.h.onPage(i, page() + 1)));
    bar.appendChild(this.pageButton("last-page", "last_page", doubleForwardIcon("h-4"), "ml-2", () => this.h.onPage(i, state.pageCount(i) - 1)));
    return bar;
  }

  private pageButton(action: string, key: string, icon: SVGElement, margin: string, onClick: () => void): HTMLButtonElement {
    const b = el("button", margin) as HTMLButtonElement;
    b.setAttribute("data-action", action);
    b.setAttribute("aria-label", this.tx(key));
    b.setAttribute("title", this.tx(key));
    b.appendChild(icon);
    b.addEventListener("click", onClick);
    return b;
  }

  private updatePageBars(i: number, state: ReviewState): void {
    const page = state.tables[i].page;
    const count = state.pageCount(i);
    for (const bar of this.pageBars) {
      // One page: nothing to page between, so the bar keeps its space in the
      // footer (as the desktop's does) but shows nothing.
      bar.className = count === 1 ? "flex items-center p-3 invisible" : "flex items-center p-3";
      Screens.setPageDisabled(bar, "first-page", "mr-2", page === 0);
      Screens.setPageDisabled(bar, "prev-page", "mr-2", page === 0);
      Screens.setPageDisabled(bar, "next-page", "ml-2", page >= count - 1);
      Screens.setPageDisabled(bar, "last-page", "ml-2", page >= count - 1);
      const label = bar.querySelector("[data-role=page-label]") as HTMLElement | null;
      // Page numbers are positions, not counts: built as plain digits so a
      // table with a thousand pages does not read "1/1,000".
      if (label) label.textContent = String(page + 1) + "/" + String(count);
    }
  }

  private static setPageDisabled(bar: HTMLElement, action: string, margin: string, disabled: boolean): void {
    const b = bar.querySelector("[data-action=" + action + "]") as HTMLButtonElement | null;
    if (!b) return;
    b.disabled = disabled;
    b.className = margin + (disabled ? " text-grey3" : " text-primary");
  }

  // The page scrolls in the host, not in the iframe, so window.scrollTo does
  // nothing here; scrollIntoView on an element inside the frame scrolls the
  // ancestor document instead, at least in WebKit (device checklist item to
  // confirm). Wrapped defensively: a Safari 12 corner case throwing here must
  // not take the render down with it.
  private scrollTableTop(): void {
    if (!this.topEl) return;
    try {
      this.topEl.scrollIntoView();
    } catch (_) {
      // deliberately swallowed
    }
  }

  // The desktop's check_box.tsx is two SVGs swapped by a class; iOS 12 draws a
  // native checkbox as a small grey square with almost no visual weight, so
  // here the input stays in the DOM (focusable, and the target of the label's
  // tap) but is visually hidden, and .mt-box draws the same two states.
  private checkBox(role: string, label: string, checked: boolean, onChange: () => void): HTMLElement {
    const wrap = el("label", "mt-check flex flex-row items-center justify-center");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "mt-visually-hidden";
    box.setAttribute("data-role", role);
    // Read out by VoiceOver in place of an unlabelled tick box. Local to this
    // frame: nothing derived from the archive is ever sent anywhere.
    box.setAttribute("aria-label", label);
    box.checked = checked;
    box.addEventListener("change", onChange);
    wrap.appendChild(box);
    // Sizing, the border, the checked fill and the tick all live in .mt-box,
    // which draws check.svg and check_active.svg without shipping either.
    wrap.appendChild(el("span", "mt-box"));
    return wrap;
  }

  private buildRow(i: number, rowIndex: number, columns: string[], cells: string[], selected: boolean): HTMLElement {
    const row = el("tr", "mt-row border-b-2 border-grey4 border-solid");
    row.setAttribute("data-row", String(rowIndex));
    if (this.expanded[rowIndex]) row.setAttribute("data-expanded", "true");

    const check = el("td", "");
    check.appendChild(this.checkBox("select", cells[0], selected, () => this.h.onToggleSelect(i, rowIndex)));
    row.appendChild(check);

    // Cells are one clipped line each until the participant taps the row; then
    // it wraps, so a long link can be read in full. The text sits in its own
    // span because an ellipsis needs a block to overflow, not a flex box.
    const toggle = (): void => {
      if (row.getAttribute("data-expanded")) { row.removeAttribute("data-expanded"); this.expanded[rowIndex] = false; }
      else { row.setAttribute("data-expanded", "true"); this.expanded[rowIndex] = true; }
      // The row just grew or shrank: the host sizes the iframe from our height,
      // so an expanded row would otherwise be cut off at the bottom.
      this.afterRender();
    };
    for (let c = 0; c < cells.length; c++) {
      const td = el("td", "");
      td.setAttribute("data-role", "cell");
      const cell = el("div", "mt-cell " + (columns[c] === DATE_COLUMN ? "mt-cell--date " : "") + CELL);
      cell.appendChild(el("span", "mt-celltext", cells[c]));
      td.appendChild(cell);
      td.addEventListener("click", toggle);
      row.appendChild(td);
    }
    return row;
  }

  // What each column would like to be, in pixels, from the longest value it
  // holds. Read-only over the rows: display work never touches what is donated
  // (ADR-0041). Taken from the whole table rather than the current page or
  // search result, so the layout does not jump around under the participant.
  private columnWidths(ts: TableState, cfg: TableConfig | undefined): number[] {
    const columns = ts.table.columns;
    const rows = ts.table.rows;
    const limit = rows.length < WIDTH_SAMPLE_ROWS ? rows.length : WIDTH_SAMPLE_ROWS;
    const out: number[] = [];
    for (let c = 0; c < columns.length; c++) {
      if (columns[c] === DATE_COLUMN) { out.push(DATE_CHARS * CHAR_PX + CELL_PADDING_PX); continue; }
      const header = cfg && cfg.headers[columns[c]] ? text(cfg.headers[columns[c]], this.locale) : columns[c];
      let chars = header.length;
      for (let r = 0; r < limit; r++) {
        const cell = rows[r][c];
        if (cell !== undefined && cell.length > chars) chars = cell.length;
      }
      if (chars < MIN_CHARS) chars = MIN_CHARS;
      if (chars > MAX_CHARS) chars = MAX_CHARS;
      out.push(chars * CHAR_PX + CELL_PADDING_PX);
    }
    return out;
  }

  // The desktop's table.tsx, on a phone: a real table inside a grey card that
  // scrolls sideways on its own rather than widening the page.
  private buildTable(i: number, ts: TableState, state: ReviewState): HTMLElement {
    const cfg = TABLES.filter((c) => c.id === ts.table.id)[0];
    const columns = ts.table.columns;

    const card = el("div", "my-2 bg-grey6 rounded-md border-grey4 border-[0.2rem]");
    const scroll = el("div", "p-3 pt-1 pb-2 max-w-full overflow-x-auto");
    const table = el("table", TABLE);
    table.setAttribute("data-role", "rows");

    const want = this.columnWidths(ts, cfg);
    // Every column is sized from its content except the widest, which is left
    // for table-fixed to hand the remainder to: the desktop's "serve the
    // narrow columns first" rule, so a 19-character timestamp shows whole and
    // the long link is the one that ellipsises.
    let widest = 0;
    for (let c = 1; c < want.length; c++) if (want[c] > want[widest]) widest = c;
    const group = document.createElement("colgroup");
    const first = document.createElement("col");
    first.style.width = CHECKBOX_COLUMN_PX + "px";
    group.appendChild(first);
    for (let c = 0; c < columns.length; c++) {
      const col = document.createElement("col");
      if (c !== widest) col.style.width = want[c] + "px";
      group.appendChild(col);
    }
    table.appendChild(group);
    // Two columns fit a 375px screen; past that the table asks for what its
    // content needs and the wrapper above scrolls it, exactly as the desktop's
    // does in a narrow window. html/body keep overflow-x hidden, so the page
    // itself never moves.
    if (columns.length > 2) {
      let total = CHECKBOX_COLUMN_PX;
      for (const w of want) total += w;
      table.style.minWidth = total + "px";
    }

    const head = document.createElement("thead");
    const headRow = el("tr", "border-b-2 border-grey4 border-solid");
    const selectAllCell = el("th", "");
    const selectAll = this.checkBox("select-all", this.tx("select_all"), state.allVisibleSelected(i), () => this.h.onToggleSelectAll(i));
    selectAllCell.appendChild(selectAll);
    headRow.appendChild(selectAllCell);
    for (const name of columns) {
      const th = el("th", "");
      // The config's translated header, falling back to the raw column name.
      const headers = cfg ? cfg.headers[name] : undefined;
      // The header rides along: "Datum en tijd" does not fit the date width on
      // one line either, and wrapping it beats truncating the column's name.
      const cell = el("div", "mt-cell text-left " + (name === DATE_COLUMN ? "mt-cell--date " : "") + CELL);
      // The same span the body cells use, so a long translated header
      // ("Gedeelde inhoud") ellipsises rather than wrapping the row taller.
      cell.appendChild(el("span", "mt-celltext", headers ? text(headers, this.locale) : name));
      th.appendChild(cell);
      headRow.appendChild(th);
    }
    head.appendChild(headRow);
    table.appendChild(head);

    const body = document.createElement("tbody");
    table.appendChild(body);
    scroll.appendChild(table);
    card.appendChild(scroll);

    const footer = el("div", "px-3 pb-1 flex justify-between items-center min-h-[2.5rem]");
    const controls = el("div", "");
    footer.appendChild(controls);
    const bar = this.buildPageBar(i, state);
    footer.appendChild(bar);
    card.appendChild(footer);

    this.rowsEl = body;
    this.selectAllEl = selectAll.querySelector("input") as HTMLInputElement;
    this.controlsEl = controls;
    this.pageBars = [bar];
    return card;
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
      // The desktop says "no data" in the summary line; on a phone the empty
      // table needs to say so where the participant is looking as well.
      const empty = el("tr", "");
      const cell = el("td", "text-grey2");
      cell.setAttribute("colspan", String(ts.table.columns.length + 1));
      cell.appendChild(el("div", CELL, this.tx("no_data")));
      empty.appendChild(cell);
      host.appendChild(empty);
      return;
    }
    const rows = ts.table.rows;
    const columns = ts.table.columns;
    for (const r of indices) host.appendChild(this.buildRow(i, r, columns, rows[r], state.isSelected(i, r)));
  }

  // scrollTop is set by the controller for a table switch and a page change;
  // not for a checkbox toggle, a search keystroke, or anything else that
  // re-renders this screen in place.
  tables(state: ReviewState, scrollTop = false): void {
    const i = state.activeIndex;
    const ts = state.tables[i];

    // Same table, search box still on screen: update in place so typing does
    // not get its input element (and keyboard focus) replaced out from under it.
    if (this.tablesIndex === i && this.searchEl && document.contains(this.searchEl)) {
      this.updateSelector(state);
      this.updateSummary(i, ts, state);
      this.updateControls(i, state);
      this.updatePageBars(i, state);
      if (this.selectAllEl) this.selectAllEl.checked = state.allVisibleSelected(i);
      this.renderRows(i, ts, state);
      this.finish();
      if (scrollTop) this.scrollTableTop();
      return;
    }

    const page = this.page(this.tx("tables_title"), this.tx("tables_body"));
    const cfg = TABLES.filter((c) => c.id === ts.table.id)[0];
    const many = state.tables.length > 1;

    if (many) page.appendChild(this.buildSelector(state));

    // consent_form_viz.tsx's TableContainer.
    const card = el("div", "p-3 flex flex-col w-full overflow-hidden border-[0.2rem] border-grey4 rounded-lg mb-4");
    // The desktop uses Title4 here; 28px is too wide a line at 375px.
    card.appendChild(el("h2", "font-title5 text-title5", this.tableTitle(ts)));
    if (cfg) card.appendChild(el("p", "font-body text-base mb-2", text(cfg.description, this.locale)));

    const summaryLine = el("div", "flex items-center mb-2");
    card.appendChild(summaryLine);

    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = this.tx("search");
    search.value = ts.query;
    search.className = SEARCH + " mb-2";
    let timer = 0;
    search.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => this.h.onQuery(i, search.value), 150);
      if (search.value.length <= 2) { window.clearTimeout(timer); this.h.onQuery(i, search.value); }
    });
    card.appendChild(search);

    this.summaryLineEl = summaryLine;
    card.appendChild(this.buildTable(i, ts, state));
    page.appendChild(card);

    // Only one table is on screen, so spell out that sharing covers them all.
    if (many) {
      const note = el("p", "font-body text-bodymedium mb-3");
      note.appendChild(el("span", "", this.tx("share_all", { n: state.tables.length })));
      note.appendChild(document.createElement("br"));
      note.appendChild(el("span", "", this.tx("all_checked")));
      page.appendChild(note);
    }

    const nav = el("div", "");
    nav.appendChild(button(this.tx("proceed"), "proceed", true, () => this.h.onProceed()));
    page.appendChild(nav);

    this.tablesIndex = i;
    this.topEl = page;
    this.searchEl = search;
    this.renderedPage = state.tables[i].page;

    this.updateSelector(state);
    this.updateSummary(i, ts, state);
    this.updateControls(i, state);
    this.updatePageBars(i, state);
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
    page.appendChild(el("p", "font-body text-bodymedium text-grey1", this.tx("donate_question")));
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
