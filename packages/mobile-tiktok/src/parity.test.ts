import { existsSync, readFileSync, readdirSync } from "fs";
import { join } from "path";
import { openExport } from "./archive";
import { runExtraction, extractUsername } from "./extract";

const DIR = join(__dirname, "..", "fixtures", "generated");

interface Expected { username: string | null; tables: { id: string; data_frame: string }[]; errors: { [k: string]: number } }

// Mirrors packages/data-collector/src/components/consent_form_viz/consent_form_viz.tsx
// (functions rowCell, columnNames, rowCount, rows, ~lines 26-56): columns are
// the object's keys in order, row i is String(df[col][String(i)]) for i in
// 0..n. A change to those functions should be traced back here.
export function desktopRows(dataFrame: string): { columns: string[]; rows: string[][] } {
  const df = JSON.parse(dataFrame) as { [col: string]: { [idx: string]: unknown } };
  const columns = Object.keys(df);
  if (columns.length === 0) return { columns, rows: [] };
  const n = Object.keys(df[columns[0]]).length;
  const rows: string[][] = [];
  for (let i = 0; i < n; i++) rows.push(columns.map((c) => String(df[c][String(i)])));
  return { columns, rows };
}

const names = readdirSync(DIR).filter((f) => f.endsWith(".zip")).map((f) => f.replace(/\.zip$/, ""));

// Guard against the suite passing vacuously (vitest runs happily with zero
// describe blocks) if fixtures/generated/ is empty or missing a fixture.
test("synthetic fixtures are present", () => {
  expect(names.length).toBeGreaterThanOrEqual(4);
  expect(names.sort()).toEqual(["json_en", "json_sparse", "txt_en", "txt_nl"]);
});

describe.each(names)("parity: %s", (name) => {
  const expectedPath = join(DIR, name + ".expected.json");
  if (!existsSync(expectedPath)) throw new Error(`missing ${expectedPath}`);
  const bytes = new Uint8Array(readFileSync(join(DIR, name + ".zip")));
  const expected = JSON.parse(readFileSync(expectedPath, "utf8")) as Expected;
  const exp = openExport(bytes);
  const actual = runExtraction(exp);

  test("username", () => {
    expect(extractUsername(exp)).toBe(expected.username);
  });

  test("same tables in the same order", () => {
    expect(actual.tables.map((t) => t.id)).toEqual(expected.tables.map((t) => t.id));
  });

  test.each(expected.tables.map((t) => t.id))("table %s rows equal", (id) => {
    const want = desktopRows(expected.tables.filter((t) => t.id === id)[0].data_frame);
    const got = actual.tables.filter((t) => t.id === id)[0];
    expect(got.columns).toEqual(want.columns);
    expect(got.rows).toEqual(want.rows);
  });
});
