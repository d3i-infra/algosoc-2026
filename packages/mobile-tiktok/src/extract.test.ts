import { readFileSync } from "fs";
import { join } from "path";
import { runExtraction, runExtractionAsync, extractTable, extractUsername } from "./extract";
import { openExport } from "./archive";
import { TABLES } from "./config";
import type { Export } from "./archive";

function jsonExport(data: unknown): Export { return { kind: "json", data }; }
function txtExport(language: "en" | "nl", files: { [k: string]: string }): Export { return { kind: "txt", language, files }; }
function counter() { const errors: { [k: string]: number } = {}; return { errors, add: (k: string) => { errors[k] = (errors[k] || 0) + 1; } }; }

test("watch history from JSON keeps export order and Amsterdam time", () => {
  const exp = jsonExport({ "Your Activity": { "Watch History": { VideoList: [
    { Date: "2024-11-27 07:28:28", Link: "https://a" },
    { Date: "2024-11-28 07:28:28", Link: "https://b" },
  ] } } });
  const t = extractTable("tiktok_watch_history", exp, counter());
  expect(t.columns).toEqual(["Date", "Link"]);
  expect(t.rows).toEqual([["2024-11-27 08:28:28", "https://a"], ["2024-11-28 08:28:28", "https://b"]]);
});

test("watch history from TXT (nl) via the parser", () => {
  const exp = txtExport("nl", { "Kijkgeschiedenis.txt": "Date: 2024-11-27 07:28:28 UTC\nLink: https://a\n\nDate: 2024-11-28 07:28:28 UTC\nLink: https://b\n" });
  expect(extractTable("tiktok_watch_history", exp, counter()).rows).toEqual([["2024-11-27 08:28:28", "https://a"], ["2024-11-28 08:28:28", "https://b"]]);
});

test("a single TXT record still yields one row", () => {
  const exp = txtExport("en", { "Watch History.txt": "Date: 2024-11-27 07:28:28 UTC\nLink: https://a\n" });
  expect(extractTable("tiktok_watch_history", exp, counter()).rows).toEqual([["2024-11-27 08:28:28", "https://a"]]);
});

test("missing section is an empty table without error", () => {
  const c = counter();
  expect(extractTable("tiktok_watch_history", jsonExport({}), c).rows).toEqual([]);
  expect(c.errors).toEqual({});
});

test("a non-record item is an error and an empty table", () => {
  const c = counter();
  const exp = jsonExport({ "Your Activity": { "Watch History": { VideoList: ["oops"] } } });
  expect(extractTable("tiktok_watch_history", exp, c).rows).toEqual([]);
  expect(Object.keys(c.errors).length).toBe(1);
});

test("activity summary uses Dutch labels and priority keys", () => {
  const exp = jsonExport({ "Your Activity": { "Activity Summary": { ActivitySummaryMap: {
    videosWatchedToTheEndSinceAccountRegistration: 12, videosCommentedOnSinceAccountRegistration: "3",
  } } } });
  expect(extractTable("tiktok_activity_summary", exp, counter()).rows).toEqual([
    ["Video's die u volledig heeft bekeken sinds uw registratie", "12"],
    ["Video's waarop u heeft gereageerd sinds uw registratie", "3"],
  ]);
});

test("settings joins keyword lists and errors when no content section", () => {
  const exp = jsonExport({ "Profile And Settings": { Settings: { SettingsMap: { "Content Preferences": {
    "Keyword filters for videos in For You feed": ["cats", "dogs"], "Keyword filters for videos in Following feed": [],
  } } } } });
  expect(extractTable("tiktok_settings", exp, counter()).rows).toEqual([
    ["Zoekwoordfilter voor video's in uw Volgend-feed", ""],
    ["Zoekwoordfilters voor video's in uw Voor Jou-feed", "cats, dogs"],
  ]);
  const c = counter();
  expect(extractTable("tiktok_settings", jsonExport({ "Profile And Settings": { Settings: { SettingsMap: { Other: {} } } } }), c).rows).toEqual([]);
  expect(Object.keys(c.errors).length).toBe(1);
});

test("comments redact emails and the username", () => {
  const exp = jsonExport({
    "Profile And Settings": { "Profile Info": { ProfileMap: { userName: "alice" } } },
    Comment: { Comments: { CommentsList: [{ Date: "2024-01-01 00:00:00", Comment: "hi alice, mail a@b.io", Photo: "", Url: "https://x" }] } },
  });
  const r = runExtraction(exp);
  const comments = r.tables.filter((t) => t.id === "tiktok_comments")[0];
  expect(comments.rows).toEqual([["2024-01-01 01:00:00", "hi [user], mail [email]", "", "https://x"]]);
});

test("ad interests reproduces the desktop column-count failure: always empty, error counted", () => {
  const c = counter();
  const exp = jsonExport({ "Your Activity": { "Ad Interests": [{ AdInterestCategories: "Cars" }] } });
  expect(extractTable("tiktok_ad_interests", exp, c).rows).toEqual([]);
  expect(Object.keys(c.errors).length).toBe(1);
});

test("runExtraction drops empty tables and keeps config order", () => {
  const exp = jsonExport({
    "Your Activity": {
      "Searches": { SearchList: [{ Date: "2024-01-01 00:00:00", SearchTerm: "q" }] },
      "Watch History": { VideoList: [{ Date: "2024-01-01 00:00:00", Link: "l" }] },
    },
  });
  expect(runExtraction(exp).tables.map((t) => t.id)).toEqual(["tiktok_watch_history", "tiktok_searches"]);
});

test("username from JSON and from TXT profile", () => {
  expect(extractUsername(jsonExport({ "Profile And Settings": { "Profile Info": { ProfileMap: { userName: "alice" } } } }))).toBe("alice");
  expect(extractUsername(jsonExport({ Profile: { "Profile Information": { ProfileMap: { userName: "bob" } } } }))).toBe("bob");
  expect(extractUsername(txtExport("en", { "Profile Information.txt": "Username: carol\nNickname: C\n" }))).toBe("carol");
  expect(extractUsername(txtExport("nl", { "Profielinformatie.txt": "Gebruikersnaam: dave\n" }))).toBe("dave");
  expect(extractUsername(jsonExport({}))).toBeNull();
});

test("runExtractionAsync yields once between tables and matches the sync result", async () => {
  const exp = openExport(new Uint8Array(readFileSync(join(__dirname, "..", "fixtures", "generated", "json_en.zip"))));
  let yields = 0;
  const got = await runExtractionAsync(exp, () => { yields++; return Promise.resolve(); });
  expect(yields).toBe(TABLES.length - 1);
  const want = runExtraction(exp);
  expect(got.tables).toEqual(want.tables);
  expect(got.errors).toEqual(want.errors);
});
