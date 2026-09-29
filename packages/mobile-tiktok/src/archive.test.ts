import { zipSync, strToU8 } from "fflate";
import { openExport, loadExport, ArchiveError, MAX_FILE_BYTES, TXT_FILES } from "./archive";

function zip(entries: { [path: string]: string }): Uint8Array {
  const input: { [path: string]: Uint8Array } = {};
  for (const k in entries) input[k] = strToU8(entries[k]);
  return zipSync(input);
}

test("detects a JSON export under either filename", () => {
  const a = openExport(zip({ "user_data_tiktok.json": '{"Your Activity": {}}' }));
  expect(a).toEqual({ kind: "json", data: { "Your Activity": {} } });
  const b = openExport(zip({ "user_data.json": '{"Activity": {}}' }));
  expect(b.kind).toBe("json");
});

test("prefers user_data_tiktok.json when both exist", () => {
  const e = openExport(zip({ "user_data_tiktok.json": '{"a":1}', "user_data.json": '{"b":2}' }));
  expect(e).toEqual({ kind: "json", data: { a: 1 } });
});

test("JSON wins when TXT marker files are also present", () => {
  const e = openExport(zip({
    "user_data_tiktok.json": '{"a":1}',
    "TikTok/Your Activity/Watch History.txt": "Date: x\nLink: y\n",
  }));
  expect(e).toEqual({ kind: "json", data: { a: 1 } });
});

test("detects a Dutch TXT export by its filenames and reads only wanted members", () => {
  const e = openExport(zip({
    "TikTok/Je activiteit/Kijkgeschiedenis.txt": "Date: 2024-01-01 00:00:00 UTC\nLink: x\n",
    "TikTok/Berichten/Directe berichten.txt": "secret",
    "TikTok/Profiel/Profielinformatie.txt": "Gebruikersnaam: someone\n",
  }));
  expect(e.kind).toBe("txt");
  if (e.kind !== "txt") return;
  expect(e.language).toBe("nl");
  expect(Object.keys(e.files).sort()).toEqual(["Kijkgeschiedenis.txt", "Profielinformatie.txt"]);
});

test("detects an English TXT export", () => {
  const e = openExport(zip({ "TikTok/Your Activity/Watch History.txt": "Date: x\nLink: y\n" }));
  expect(e.kind === "txt" && e.language).toBe("en");
});

test("ambiguous basename counts as missing", () => {
  const e = openExport(zip({
    "TikTok/A/Watch History.txt": "Date: 1\nLink: a\n",
    "TikTok/B/Watch History.txt": "Date: 2\nLink: b\n",
    "TikTok/Your Activity/Searches.txt": "Date: 1\nSearch Term: q\n",
  }));
  expect(e.kind === "txt" && Object.keys(e.files)).toEqual(["Searches.txt"]);
});

test("rejects a zip with none of the known files", () => {
  expect(() => openExport(zip({ "readme.txt": "hi" }))).toThrow(ArchiveError);
  expect(kindOf(() => openExport(zip({ "readme.txt": "hi" })))).toBe("not_tiktok");
});

function kindOf(fn: () => unknown): string {
  try { fn(); return "none"; } catch (err) { return (err as ArchiveError).kind; }
}

test("rejects bytes that are not a zip", () => {
  expect(kindOf(() => openExport(strToU8("not a zip")))).toBe("unreadable");
});

test("rejects a JSON member that does not parse", () => {
  expect(kindOf(() => openExport(zip({ "user_data_tiktok.json": "{oops" })))).toBe("unreadable");
});

test("openExport refuses a JSON member whose uncompressed size exceeds the cap", () => {
  const content = '{"a":1}';
  const bytes = zip({ "user_data_tiktok.json": content });
  const cap = strToU8(content).length - 1;
  expect(kindOf(() => openExport(bytes, cap))).toBe("too_large");
});

test("openExport refuses a TXT member whose uncompressed size exceeds the cap", () => {
  const content = "Date: x\nLink: y\n";
  const bytes = zip({ "TikTok/Your Activity/Watch History.txt": content });
  const cap = strToU8(content).length - 1;
  expect(kindOf(() => openExport(bytes, cap))).toBe("too_large");
});

test("openExport accepts a member whose uncompressed size exactly equals the cap", () => {
  const content = '{"ok":true}';
  const bytes = zip({ "user_data_tiktok.json": content });
  const cap = strToU8(content).length;
  const e = openExport(bytes, cap);
  expect(e).toEqual({ kind: "json", data: { ok: true } });
});

test("loadExport refuses by File.size before reading", async () => {
  const big = { size: MAX_FILE_BYTES + 1, name: "x.zip" } as unknown as File;
  await expect(loadExport(big)).rejects.toMatchObject({ kind: "too_large" });
});

test("loadExport reads a real File through FileReader", async () => {
  const bytes = zip({ "user_data_tiktok.json": '{"ok":true}' });
  const file = new File([bytes as BlobPart], "TikTok_Data_1.zip");
  const e = await loadExport(file);
  expect(e).toEqual({ kind: "json", data: { ok: true } });
});

test("TXT_FILES lists both languages for all 13 tables", () => {
  expect(TXT_FILES.nl.length).toBe(TXT_FILES.en.length);
  expect(TXT_FILES.en).toContain("Watch History.txt");
  expect(TXT_FILES.nl).toContain("Kijkgeschiedenis.txt");
});
