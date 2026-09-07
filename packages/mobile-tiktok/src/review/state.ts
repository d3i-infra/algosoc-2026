import type { Table } from "../extract";

export const PAGE_SIZE = 50;

// A month key is the "YYYY-MM" prefix of a Date cell; anything that does not
// start like a date is left out of the index rather than guessed at.
const MONTH_PREFIX = /^[0-9]{4}-[0-9]{2}/;

export interface TableState {
  table: Table;
  deleted: Uint8Array;
  deletedCount: number;
  selected: Uint8Array;
  selectedCount: number;
  query: string;
  matches: number[] | null;
  page: number;
  // Derived views over the rows, held until a mutation drops them. Every
  // in-place render asks for these several times, and on a 65k-row watch
  // history each rebuild is a full pass over the table.
  visibleCache: number[] | null;
  monthsCache: string[] | null;
}

export type UndoEntry = { tableIndex: number; rows: number[] };

function rowMatches(row: string[], needle: string): boolean {
  for (let i = 0; i < row.length; i++) {
    if (row[i].toLowerCase().indexOf(needle) >= 0) return true;
  }
  return false;
}

export class ReviewState {
  readonly tables: TableState[];
  activeIndex = 0;
  private undoStack: UndoEntry[] = [];

  constructor(tables: Table[]) {
    this.tables = tables.map((table) => ({
      table,
      deleted: new Uint8Array(table.rows.length),
      deletedCount: 0,
      selected: new Uint8Array(table.rows.length),
      selectedCount: 0,
      query: "",
      matches: null,
      page: 0,
      visibleCache: null,
      monthsCache: null,
    }));
  }

  // Callers may keep and mutate what they get back, so the cached array itself
  // never leaves this class through here.
  visibleRows(tableIndex: number): number[] {
    return this.visible(tableIndex).slice();
  }

  private visible(t: number): number[] {
    const ts = this.tables[t];
    if (ts.visibleCache !== null) return ts.visibleCache;
    let out: number[];
    if (ts.matches !== null) {
      out = ts.matches.slice();
    } else {
      out = [];
      for (let i = 0; i < ts.table.rows.length; i++) if (!ts.deleted[i]) out.push(i);
    }
    ts.visibleCache = out;
    return out;
  }

  // Anything that changes which rows are visible drops both derived views.
  // Selection and paging deliberately do not: they change nothing here.
  private invalidate(t: TableState): void {
    t.visibleCache = null;
    t.monthsCache = null;
  }

  setQuery(tableIndex: number, query: string): void {
    const t = this.tables[tableIndex];
    t.query = query;
    this.recompute(t);
    this.invalidate(t);
    // A new result set has its own pages; start at the top of it.
    t.page = 0;
    // And its own selection: "Remove selected (N)" must never count rows the
    // current search has hidden away.
    this.clearSelection(tableIndex);
  }

  // Paging is display state over visibleRows: it never changes which rows are
  // donated, only how many of them are on screen at once.
  pageCount(tableIndex: number): number {
    const n = this.visible(tableIndex).length;
    return Math.max(1, Math.ceil(n / PAGE_SIZE));
  }

  pageRows(tableIndex: number): number[] {
    const t = this.tables[tableIndex];
    const start = t.page * PAGE_SIZE;
    return this.visible(tableIndex).slice(start, start + PAGE_SIZE);
  }

  setPage(tableIndex: number, page: number): void {
    const t = this.tables[tableIndex];
    const last = this.pageCount(tableIndex) - 1;
    t.page = page < 0 ? 0 : page > last ? last : page;
  }

  // Deletions can leave the current page past the end of the list.
  private clampPage(tableIndex: number): void {
    this.setPage(tableIndex, this.tables[tableIndex].page);
  }

  private dateColumn(tableIndex: number): number {
    return this.tables[tableIndex].table.columns.indexOf("Date");
  }

  // The returned array is the cached one: read it, do not mutate it.
  months(tableIndex: number): string[] {
    const ts = this.tables[tableIndex];
    if (ts.monthsCache !== null) return ts.monthsCache;
    const col = this.dateColumn(tableIndex);
    if (col < 0) { ts.monthsCache = []; return ts.monthsCache; }
    const rows = ts.table.rows;
    const visible = this.visible(tableIndex);
    const seen: { [month: string]: boolean } = {};
    const out: string[] = [];
    for (const r of visible) {
      const cell = rows[r][col];
      if (cell === undefined || !MONTH_PREFIX.test(cell)) continue;
      const month = cell.slice(0, 7);
      if (seen[month]) continue;
      seen[month] = true;
      out.push(month);
    }
    ts.monthsCache = out;
    return out;
  }

  jumpToMonth(tableIndex: number, month: string): void {
    const col = this.dateColumn(tableIndex);
    if (col < 0 || month === "") return;
    const rows = this.tables[tableIndex].table.rows;
    const visible = this.visible(tableIndex);
    for (let i = 0; i < visible.length; i++) {
      const cell = rows[visible[i]][col];
      if (cell !== undefined && cell.indexOf(month) === 0) {
        this.setPage(tableIndex, Math.floor(i / PAGE_SIZE));
        return;
      }
    }
  }

  private recompute(t: TableState): void {
    const needle = t.query.trim().toLowerCase();
    if (needle === "") { t.matches = null; return; }
    const out: number[] = [];
    const rows = t.table.rows;
    for (let i = 0; i < rows.length; i++) {
      if (!t.deleted[i] && rowMatches(rows[i], needle)) out.push(i);
    }
    t.matches = out;
  }

  // Selection is display state: it marks rows the participant has ticked and
  // never changes `deleted` except through deleteSelected below.
  toggleSelected(tableIndex: number, row: number): void {
    const t = this.tables[tableIndex];
    if (t.deleted[row]) return;
    if (t.selected[row]) { t.selected[row] = 0; t.selectedCount--; }
    else { t.selected[row] = 1; t.selectedCount++; }
  }

  isSelected(tableIndex: number, row: number): boolean {
    return this.tables[tableIndex].selected[row] === 1;
  }

  selectedCount(tableIndex: number): number {
    return this.tables[tableIndex].selectedCount;
  }

  clearSelection(tableIndex: number): void {
    const t = this.tables[tableIndex];
    if (t.selectedCount === 0) return;
    t.selected.fill(0);
    t.selectedCount = 0;
  }

  deleteSelected(tableIndex: number): number {
    const t = this.tables[tableIndex];
    const rows: number[] = [];
    for (let i = 0; i < t.selected.length; i++) {
      if (t.selected[i] && !t.deleted[i]) rows.push(i);
    }
    this.clearSelection(tableIndex);
    if (rows.length === 0) return 0;
    for (const r of rows) { t.deleted[r] = 1; }
    t.deletedCount += rows.length;
    // One entry, so a single Undo brings the whole batch back.
    this.undoStack.push({ tableIndex, rows });
    this.recompute(t);
    this.invalidate(t);
    this.clampPage(tableIndex);
    return rows.length;
  }

  deleteRow(tableIndex: number, row: number): void {
    const t = this.tables[tableIndex];
    if (t.deleted[row]) return;
    t.deleted[row] = 1;
    t.deletedCount++;
    if (t.selected[row]) { t.selected[row] = 0; t.selectedCount--; }
    this.undoStack.push({ tableIndex, rows: [row] });
    if (t.matches !== null) {
      const idx = t.matches.indexOf(row);
      if (idx >= 0) t.matches.splice(idx, 1);
    }
    this.invalidate(t);
    this.clampPage(tableIndex);
  }

  deleteMatches(tableIndex: number): number {
    const t = this.tables[tableIndex];
    if (t.matches === null || t.matches.length === 0) return 0;
    const rows = t.matches.slice();
    for (const r of rows) {
      t.deleted[r] = 1;
      if (t.selected[r]) { t.selected[r] = 0; t.selectedCount--; }
    }
    t.deletedCount += rows.length;
    this.undoStack.push({ tableIndex, rows });
    this.recompute(t);
    this.invalidate(t);
    this.clampPage(tableIndex);
    return rows.length;
  }

  canUndo(): boolean { return this.undoStack.length > 0; }

  undo(): boolean {
    const entry = this.undoStack.pop();
    if (!entry) return false;
    const t = this.tables[entry.tableIndex];
    for (const r of entry.rows) { if (t.deleted[r]) { t.deleted[r] = 0; t.deletedCount--; } }
    this.recompute(t);
    this.invalidate(t);
    this.clampPage(entry.tableIndex);
    return true;
  }

  keptCount(tableIndex: number): number {
    const t = this.tables[tableIndex];
    return t.table.rows.length - t.deletedCount;
  }
}
