import { existsSync, readdirSync, readFileSync } from "fs";
import { join } from "path";
import { openExport } from "./archive";
import type { Export } from "./archive";
import { getFirst } from "./lookup";
import { runExtraction, extractUsername } from "./extract";

// Real exports dropped into fixtures/ddp/ (git-ignored, ADR-0014). No expected
// files exist for them; this only proves they open and extract without throwing,
// and prints table sizes for the person running it.
const DIR = join(__dirname, "..", "fixtures", "ddp");

// TikTok's export options are per category, so a genuine export can ship no
// profile section at all — and then there is no own-username to redact. Where
// the section IS there, the lookup has to find a username: that is what keeps
// the redaction in extract.ts honest against real key spellings.
function hasProfileSection(exp: Export): boolean {
  if (exp.kind === "txt") {
    return exp.files["Profile Information.txt"] !== undefined || exp.files["Profielinformatie.txt"] !== undefined;
  }
  return getFirst(exp.data,
    ["Profile And Settings", "Profile Info"],
    ["Profile", "Profile Information"],
    ["Profile", "Profile Info"],
    ["Profile And Settings", "Profile Information"]) !== undefined;
}

const zips = existsSync(DIR) ? readdirSync(DIR).filter((f) => f.endsWith(".zip")) : [];

const run = zips.length ? describe : describe.skip;
run("real exports in fixtures/ddp", () => {
  test.each(zips)("%s opens and extracts", (name) => {
    const exp = openExport(new Uint8Array(readFileSync(join(DIR, name))));
    // Only ever printed masked: the username is the thing redaction removes
    // from comments and searches, so it must never be echoed to a terminal.
    const username = extractUsername(exp);
    console.log(name, "username", username === null ? "absent" : "present");
    const result = runExtraction(exp);
    for (const t of result.tables) console.log(name, t.id, t.rows.length);
    if (hasProfileSection(exp)) {
      expect(typeof username).toBe("string");
      expect(String(username).length).toBeGreaterThan(0);
    }
    expect(result.tables.length).toBeGreaterThan(0);
  });
});
