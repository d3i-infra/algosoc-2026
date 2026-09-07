import { serializePayload, DECLINE_PAYLOAD } from "./payload";
import { ReviewState } from "./review/state";
import type { Table } from "./extract";

const tables: Table[] = [
  { id: "tiktok_watch_history", columns: ["Date", "Link"], rows: [["2024-01-01 01:00:00", "https://a"], ["2024-01-02 01:00:00", "https://b"]] },
  { id: "tiktok_searches", columns: ["Date", "SearchTerm"], rows: [["2024-01-01 01:00:00", "q \"quoted\" \\ slash / ünïcode"]] },
];

test("serializes every non-deleted row keyed by raw column name with the deleted count", () => {
  const s = new ReviewState(tables);
  s.deleteRow(0, 0);
  const parsed = JSON.parse(serializePayload(s));
  expect(parsed).toEqual([
    { tiktok_watch_history: [{ Date: "2024-01-02 01:00:00", Link: "https://b" }], "deleted row count": "1" },
    { tiktok_searches: [{ Date: "2024-01-01 01:00:00", SearchTerm: "q \"quoted\" \\ slash / ünïcode" }], "deleted row count": "0" },
  ]);
});

test("matches JSON.stringify of the same structure byte for byte", () => {
  const s = new ReviewState(tables);
  const expected = JSON.stringify([
    { tiktok_watch_history: [{ Date: "2024-01-01 01:00:00", Link: "https://a" }, { Date: "2024-01-02 01:00:00", Link: "https://b" }], "deleted row count": "0" },
    { tiktok_searches: [{ Date: "2024-01-01 01:00:00", SearchTerm: "q \"quoted\" \\ slash / ünïcode" }], "deleted row count": "0" },
  ]);
  expect(serializePayload(s)).toBe(expected);
});

test("a table with every row deleted still appears with an empty list", () => {
  const s = new ReviewState([tables[1]]);
  s.deleteRow(0, 0);
  expect(JSON.parse(serializePayload(s))).toEqual([{ tiktok_searches: [], "deleted row count": "1" }]);
});

test("decline literal", () => {
  expect(DECLINE_PAYLOAD).toBe('{"status": "data_submission declined"}');
});

test("a query and a windowed view never shrink the payload", () => {
  const rows: string[][] = [];
  for (let i = 0; i < 50; i++) rows.push(["2024-01-01 01:00:00", "https://v/" + i]);
  const s = new ReviewState([{ id: "tiktok_watch_history", columns: ["Date", "Link"], rows }, tables[1]]);
  s.deleteRow(0, 3);
  s.setQuery(0, "https://v/7");   // matches a handful of rows; the list shows only those
  s.activeIndex = 1;              // and the participant is looking at another table
  const parsed = JSON.parse(serializePayload(s)) as { [k: string]: unknown }[];
  const kept = parsed[0].tiktok_watch_history as { Date: string; Link: string }[];
  expect(kept.length).toBe(49);
  for (let i = 0; i < 50; i++) {
    expect(kept.filter((r) => r.Link === "https://v/" + i).length).toBe(i === 3 ? 0 : 1);
  }
  expect(parsed[0]["deleted row count"]).toBe("1");
  expect((parsed[1].tiktok_searches as unknown[]).length).toBe(1);
});

test("a row with fewer cells than columns is refused, not written as invalid JSON", () => {
  const s = new ReviewState([{ id: "tiktok_searches", columns: ["Date", "SearchTerm"], rows: [["2024-01-01 01:00:00"]] }]);
  expect(() => serializePayload(s)).toThrow("payload_row_shape");
});
