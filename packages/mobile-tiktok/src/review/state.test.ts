import { ReviewState, PAGE_SIZE } from "./state";
import type { Table } from "../extract";

function table(id: string, rows: string[][]): Table { return { id, columns: ["Date", "Link"], rows }; }

const t1 = table("a", [["2024-01-01", "https://x/Cats"], ["2024-01-02", "https://x/dogs"], ["2024-01-03", "https://x/cats2"]]);
const t2 = table("b", [["2024-02-01", "u"]]);

test("visible rows are all rows initially", () => {
  const s = new ReviewState([t1, t2]);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
  expect(s.keptCount(0)).toBe(3);
});

test("query filters case-insensitively across cells", () => {
  const s = new ReviewState([t1]);
  s.setQuery(0, "CATS");
  expect(s.visibleRows(0)).toEqual([0, 2]);
  s.setQuery(0, "2024-01-02");
  expect(s.visibleRows(0)).toEqual([1]);
  s.setQuery(0, "");
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});

test("deleteRow hides the row, counts it, and can be undone", () => {
  const s = new ReviewState([t1]);
  s.deleteRow(0, 1);
  expect(s.visibleRows(0)).toEqual([0, 2]);
  expect(s.tables[0].deletedCount).toBe(1);
  expect(s.canUndo()).toBe(true);
  expect(s.undo()).toBe(true);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
  expect(s.tables[0].deletedCount).toBe(0);
  expect(s.undo()).toBe(false);
});

test("deleteMatches removes every match and undo restores them all", () => {
  const s = new ReviewState([t1]);
  s.setQuery(0, "cats");
  expect(s.deleteMatches(0)).toBe(2);
  expect(s.visibleRows(0)).toEqual([]);
  s.setQuery(0, "");
  expect(s.visibleRows(0)).toEqual([1]);
  expect(s.tables[0].deletedCount).toBe(2);
  s.undo();
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});

test("deleting an already deleted row is a no-op", () => {
  const s = new ReviewState([t1]);
  s.deleteRow(0, 0);
  s.deleteRow(0, 0);
  expect(s.tables[0].deletedCount).toBe(1);
});

test("deleteMatches with no query deletes nothing", () => {
  const s = new ReviewState([t1]);
  expect(s.deleteMatches(0)).toBe(0);
});

test("undo is per action across tables", () => {
  const s = new ReviewState([t1, t2]);
  s.deleteRow(0, 0);
  s.deleteRow(1, 0);
  s.undo();
  expect(s.visibleRows(1)).toEqual([0]);
  expect(s.visibleRows(0)).toEqual([1, 2]);
});

test("visibleRows returns a copy that won't corrupt state", () => {
  const s = new ReviewState([t1]);
  s.setQuery(0, "cats");
  const visible1 = s.visibleRows(0);
  expect(visible1).toEqual([0, 2]);

  // Mutate the returned array
  visible1.length = 0;

  // deleteMatches should still work correctly
  expect(s.deleteMatches(0)).toBe(2);

  // visibleRows should still report correctly before deletion
  s.setQuery(0, "");
  expect(s.visibleRows(0)).toEqual([1]);
});

test("deleteRow with query active preserves order and undo restores", () => {
  const s = new ReviewState([t1]);
  s.setQuery(0, "cats");
  expect(s.visibleRows(0)).toEqual([0, 2]);

  // Delete one match
  s.deleteRow(0, 0);
  expect(s.visibleRows(0)).toEqual([2]);

  // Delete another match
  s.deleteRow(0, 2);
  expect(s.visibleRows(0)).toEqual([]);

  // Undo restores in reverse order
  s.undo();
  expect(s.visibleRows(0)).toEqual([2]);
  s.undo();
  expect(s.visibleRows(0)).toEqual([0, 2]);
});

test("toggleSelected tracks a per-row selection and counts it", () => {
  const s = new ReviewState([t1]);
  expect(s.isSelected(0, 1)).toBe(false);
  expect(s.selectedCount(0)).toBe(0);
  s.toggleSelected(0, 1);
  expect(s.isSelected(0, 1)).toBe(true);
  expect(s.selectedCount(0)).toBe(1);
  s.toggleSelected(0, 2);
  expect(s.selectedCount(0)).toBe(2);
  s.toggleSelected(0, 1);
  expect(s.isSelected(0, 1)).toBe(false);
  expect(s.selectedCount(0)).toBe(1);
  expect(s.tables[0].deletedCount).toBe(0);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});

test("clearSelection drops every selected row without deleting anything", () => {
  const s = new ReviewState([t1]);
  s.toggleSelected(0, 0);
  s.toggleSelected(0, 2);
  s.clearSelection(0);
  expect(s.selectedCount(0)).toBe(0);
  expect(s.isSelected(0, 0)).toBe(false);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
  expect(s.canUndo()).toBe(false);
});

test("deleteSelected removes the selection in one undo step and clears it", () => {
  const s = new ReviewState([t1]);
  s.toggleSelected(0, 0);
  s.toggleSelected(0, 2);
  expect(s.deleteSelected(0)).toBe(2);
  expect(s.visibleRows(0)).toEqual([1]);
  expect(s.tables[0].deletedCount).toBe(2);
  expect(s.selectedCount(0)).toBe(0);
  expect(s.undo()).toBe(true);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
  expect(s.tables[0].deletedCount).toBe(0);
  // Undo restores the rows, not the selection.
  expect(s.selectedCount(0)).toBe(0);
  expect(s.canUndo()).toBe(false);
});

test("deleteSelected with nothing selected changes nothing", () => {
  const s = new ReviewState([t1]);
  expect(s.deleteSelected(0)).toBe(0);
  expect(s.canUndo()).toBe(false);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});

test("selecting an already deleted row is a no-op", () => {
  const s = new ReviewState([t1]);
  s.deleteRow(0, 1);
  s.toggleSelected(0, 1);
  expect(s.isSelected(0, 1)).toBe(false);
  expect(s.selectedCount(0)).toBe(0);
  expect(s.deleteSelected(0)).toBe(0);
  expect(s.tables[0].deletedCount).toBe(1);
});

test("selection is per table", () => {
  const s = new ReviewState([t1, t2]);
  s.toggleSelected(0, 0);
  expect(s.selectedCount(0)).toBe(1);
  expect(s.selectedCount(1)).toBe(0);
  expect(s.isSelected(1, 0)).toBe(false);
  s.toggleSelected(1, 0);
  expect(s.deleteSelected(1)).toBe(1);
  expect(s.visibleRows(1)).toEqual([]);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
  expect(s.selectedCount(0)).toBe(1);
});

test("deleteSelected drops the rows from an active query result", () => {
  const s = new ReviewState([t1]);
  s.setQuery(0, "cats");
  expect(s.visibleRows(0)).toEqual([0, 2]);
  s.toggleSelected(0, 0);
  expect(s.deleteSelected(0)).toBe(1);
  expect(s.visibleRows(0)).toEqual([2]);
});

function dated(n: number): Table {
  const rows: string[][] = [];
  for (let i = 0; i < n; i++) {
    const month = 1 + Math.floor(i / 40);
    const day = 1 + (i % 28);
    const mm = month < 10 ? "0" + month : String(month);
    const dd = day < 10 ? "0" + day : String(day);
    rows.push(["2024-" + mm + "-" + dd + " 09:00:00", "https://x/v" + i]);
  }
  return { id: "tiktok_watch_history", columns: ["Date", "Link"], rows };
}

const undatedTable: Table = { id: "tiktok_hashtag", columns: ["HashtagName", "HashtagLink"], rows: [["#a", "https://x/a"], ["#b", "https://x/b"]] };

test("PAGE_SIZE is 50 and pages slice the visible rows", () => {
  expect(PAGE_SIZE).toBe(50);
  const s = new ReviewState([dated(120)]);
  expect(s.pageCount(0)).toBe(3);
  expect(s.pageRows(0).length).toBe(50);
  expect(s.pageRows(0)[0]).toBe(0);
  expect(s.pageRows(0)[49]).toBe(49);
  s.setPage(0, 1);
  expect(s.pageRows(0)[0]).toBe(50);
  expect(s.pageRows(0).length).toBe(50);
  s.setPage(0, 2);
  expect(s.pageRows(0)).toEqual([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119]);
});

test("an exact multiple of the page size has no trailing empty page", () => {
  const s = new ReviewState([dated(100)]);
  expect(s.pageCount(0)).toBe(2);
  s.setPage(0, 1);
  expect(s.pageRows(0).length).toBe(50);
});

test("a table that fits on one page, and an empty result, report one page", () => {
  const s = new ReviewState([dated(6)]);
  expect(s.pageCount(0)).toBe(1);
  expect(s.pageRows(0).length).toBe(6);
  s.setQuery(0, "no-such-thing");
  expect(s.pageCount(0)).toBe(1);
  expect(s.pageRows(0)).toEqual([]);
});

test("setPage clamps to the available pages", () => {
  const s = new ReviewState([dated(120)]);
  s.setPage(0, 99);
  expect(s.tables[0].page).toBe(2);
  s.setPage(0, -3);
  expect(s.tables[0].page).toBe(0);
});

test("months lists the distinct year-months of a dated table in first-seen order", () => {
  const s = new ReviewState([dated(120)]);
  expect(s.months(0)).toEqual(["2024-01", "2024-02", "2024-03"]);
});

test("months is empty for a table with no Date column", () => {
  const s = new ReviewState([undatedTable]);
  expect(s.months(0)).toEqual([]);
});

test("months follows the visible rows", () => {
  const s = new ReviewState([dated(120)]);
  s.setQuery(0, "2024-03");
  expect(s.months(0)).toEqual(["2024-03"]);
});

test("jumpToMonth lands on the page holding that month's first row", () => {
  const s = new ReviewState([dated(120)]);
  s.jumpToMonth(0, "2024-02");
  expect(s.tables[0].page).toBe(0);   // row 40 is still on page 0
  s.jumpToMonth(0, "2024-03");
  expect(s.tables[0].page).toBe(1);   // row 80
  s.jumpToMonth(0, "2024-09");
  expect(s.tables[0].page).toBe(1);   // unknown month: no move
  s.jumpToMonth(0, "2024-01");
  expect(s.tables[0].page).toBe(0);
});

test("setQuery resets the page", () => {
  const s = new ReviewState([dated(120)]);
  s.setPage(0, 2);
  s.setQuery(0, "https://");
  expect(s.tables[0].page).toBe(0);
});

test("deleting the last row of the last page steps back a page", () => {
  const s = new ReviewState([dated(51)]);
  s.setPage(0, 1);
  expect(s.pageRows(0)).toEqual([50]);
  s.toggleSelected(0, 50);
  s.deleteSelected(0);
  expect(s.tables[0].page).toBe(0);
  expect(s.pageRows(0).length).toBe(50);
  s.undo();
  expect(s.pageCount(0)).toBe(2);
  expect(s.tables[0].page).toBe(0);
});

test("deleteRow and deleteMatches also clamp the page", () => {
  const s = new ReviewState([dated(51)]);
  s.setPage(0, 1);
  s.deleteRow(0, 50);
  expect(s.tables[0].page).toBe(0);
  const s2 = new ReviewState([dated(51)]);
  s2.setPage(0, 1);
  s2.setQuery(0, "");
  s2.setPage(0, 1);
  s2.setQuery(0, "v50");
  expect(s2.tables[0].page).toBe(0);
  s2.deleteMatches(0);
  expect(s2.tables[0].page).toBe(0);
});

test("paging is per table", () => {
  const s = new ReviewState([dated(120), dated(120)]);
  s.setPage(0, 2);
  expect(s.tables[0].page).toBe(2);
  expect(s.tables[1].page).toBe(0);
  expect(s.pageRows(1)[0]).toBe(0);
});

test("visible rows and months are computed once and reused until something changes", () => {
  const s = new ReviewState([dated(120)]);
  const months = s.months(0);
  expect(s.months(0)).toBe(months);                       // cached, not rescanned
  expect(s.visibleRows(0)).toEqual(s.visibleRows(0));
  expect(s.visibleRows(0)).not.toBe(s.visibleRows(0));    // still a copy per caller
  // Selection is not visibility: it must not throw the caches away.
  s.toggleSelected(0, 0);
  expect(s.months(0)).toBe(months);
  s.setPage(0, 1);
  expect(s.months(0)).toBe(months);
});

test("deleting a month's last row drops that month from the index", () => {
  const rows = [["2024-01-01 09:00:00", "https://x/a"], ["2024-02-01 09:00:00", "https://x/b"], ["2024-02-02 09:00:00", "https://x/c"]];
  const s = new ReviewState([{ id: "tiktok_watch_history", columns: ["Date", "Link"], rows }]);
  expect(s.months(0)).toEqual(["2024-01", "2024-02"]);
  s.toggleSelected(0, 0);
  s.deleteSelected(0);
  expect(s.months(0)).toEqual(["2024-02"]);
  expect(s.visibleRows(0)).toEqual([1, 2]);
  s.undo();
  expect(s.months(0)).toEqual(["2024-01", "2024-02"]);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});

test("deleteRow, deleteMatches and setQuery all invalidate the caches", () => {
  const rows = [["2024-01-01 09:00:00", "https://x/a"], ["2024-02-01 09:00:00", "https://x/b"], ["2024-03-01 09:00:00", "https://x/c"]];
  const s = new ReviewState([{ id: "tiktok_watch_history", columns: ["Date", "Link"], rows }]);
  expect(s.months(0)).toEqual(["2024-01", "2024-02", "2024-03"]);
  s.deleteRow(0, 2);
  expect(s.months(0)).toEqual(["2024-01", "2024-02"]);
  expect(s.visibleRows(0)).toEqual([0, 1]);
  s.setQuery(0, "2024-02");
  expect(s.months(0)).toEqual(["2024-02"]);
  expect(s.visibleRows(0)).toEqual([1]);
  s.deleteMatches(0);
  expect(s.months(0)).toEqual([]);
  expect(s.visibleRows(0)).toEqual([]);
  s.setQuery(0, "");
  expect(s.months(0)).toEqual(["2024-01"]);
});

test("a new search clears the selection", () => {
  const s = new ReviewState([t1]);
  s.toggleSelected(0, 0);
  expect(s.selectedCount(0)).toBe(1);
  s.setQuery(0, "cats");
  // Remove selected must only ever count rows reachable under the search on
  // screen, so a changed search starts the selection over.
  expect(s.selectedCount(0)).toBe(0);
  expect(s.isSelected(0, 0)).toBe(false);
  s.toggleSelected(0, 2);
  s.setQuery(0, "");
  expect(s.selectedCount(0)).toBe(0);
  expect(s.deleteSelected(0)).toBe(0);
  expect(s.visibleRows(0)).toEqual([0, 1, 2]);
});
