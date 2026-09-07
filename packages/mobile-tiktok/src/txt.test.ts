import { parseTikTokTxt, parseValue, isEmptySentinel } from "./txt";

test("empty file or a lone sentinel is null", () => {
  expect(parseTikTokTxt("")).toBeNull();
  expect(parseTikTokTxt("\n\n")).toBeNull();
  expect(parseTikTokTxt("You have no data in this section\n")).toBeNull();
  expect(parseTikTokTxt("Dit gedeelte bevat geen gegevens")).toBeNull();
});

test("single key-value block is a flat record", () => {
  expect(parseTikTokTxt("Username: alice\nNickname: Al\n")).toEqual({ Username: "alice", Nickname: "Al" });
});

test("repeated identical-key blocks are a list of records", () => {
  const text = "Date: 2024-01-01 10:00:00 UTC\nLink: https://a\n\nDate: 2024-01-02 10:00:00 UTC\nLink: https://b\n\n";
  expect(parseTikTokTxt(text)).toEqual([
    { Date: "2024-01-01 10:00:00 UTC", Link: "https://a" },
    { Date: "2024-01-02 10:00:00 UTC", Link: "https://b" },
  ]);
});

test("values keep colons after the first", () => {
  expect(parseTikTokTxt("Date: 2024-01-01 10:00:00 UTC\nLink: https://x\n\nDate: 2024-01-01 11:00:00 UTC\nLink: https://y\n"))
    .toEqual([{ Date: "2024-01-01 10:00:00 UTC", Link: "https://x" }, { Date: "2024-01-01 11:00:00 UTC", Link: "https://y" }]);
});

test("diverging keys fall back to generic nested parsing", () => {
  const text = "Date: 1\nLink: a\n\nDate: 2\nOther: b\n";
  expect(parseTikTokTxt(text)).toEqual({ Date: 2, Link: "a", Other: "b" });
});

test("section headers open nested dicts", () => {
  const text = "Content Preferences:\nKeyword filters for videos in For You feed: [cats, dogs]\n\nPrivacy\nPrivate Account: Off\n";
  // Python keeps a header's trailing colon: section_name = block[0].strip()
  expect(parseTikTokTxt(text)).toEqual({
    "Content Preferences:": { "Keyword filters for videos in For You feed": ["cats", "dogs"] },
    Privacy: { "Private Account": "Off" },
  });
});

test("a header-looking single line block stays a plain key", () => {
  expect(parseTikTokTxt("(Note: something\n\nVideos shared since account registration: 3\nVideos watched to the end since account registration: 12\n"))
    .toEqual({ "(Note": "something", "Videos shared since account registration": 3, "Videos watched to the end since account registration": 12 });
});

test("a header followed by a sentinel line is an empty section", () => {
  expect(parseTikTokTxt("Section A:\nYou have no data in this section\n")).toEqual({ "Section A:": {} });
});

test("parseValue coercions", () => {
  expect(parseValue(" [] ")).toEqual([]);
  expect(parseValue("[a, b ,c]")).toEqual(["a", "b", "c"]);
  expect(parseValue("[ ]")).toEqual([]);
  expect(parseValue("N/A")).toBeNull();
  expect(parseValue("n.v.t.")).toBeNull();
  expect(parseValue("None")).toBeNull();
  expect(parseValue(" 42 ")).toBe(42);
  expect(parseValue("-7")).toBe(-7);
  expect(parseValue("007")).toBe(7);
  expect(parseValue("4.5")).toBe("4.5");
  expect(parseValue("https://x:1")).toBe("https://x:1");
});

test("sentinels are case-insensitive and trimmed", () => {
  expect(isEmptySentinel("  YOU HAVE NO DATA IN THIS SECTION ")).toBe(true);
  expect(isEmptySentinel("Er staan geen gegevens in dit gedeelte")).toBe(true);
  expect(isEmptySentinel("Je hebt geen informatie over platforms van derden")).toBe(true);
  expect(isEmptySentinel("something else")).toBe(false);
});

test("trailing blank lines and CRLF are tolerated", () => {
  expect(parseTikTokTxt("A: 1\r\nB: 2\r\n\r\n\r\n")).toEqual({ A: 1, B: 2 });
});
