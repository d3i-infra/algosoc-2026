import { T, formatCount, t } from "./text";

test("formatCount groups digits by locale", () => {
  expect(formatCount(200000, "en")).toBe("200,000");
  expect(formatCount(200000, "nl")).toBe("200.000");
});

test("formatCount leaves small counts unaffected", () => {
  expect(formatCount(1, "en")).toBe("1");
  expect(formatCount(0, "nl")).toBe("0");
});

test("formatCount falls back to a plain string if toLocaleString throws", () => {
  const proto = Number.prototype as unknown as { toLocaleString: () => string };
  const real = proto.toLocaleString;
  proto.toLocaleString = () => { throw new Error("no ICU"); };
  try {
    expect(formatCount(1234, "en")).toBe("1234");
  } finally {
    proto.toLocaleString = real;
  }
});

test("t() formats numeric vars through formatCount, leaving string vars alone", () => {
  expect(t("rows_kept", "en", { kept: 200000, deleted: 3 })).toBe("200,000 rows, 3 removed");
  expect(t("rows_kept", "nl", { kept: 200000, deleted: 3 })).toBe("200.000 rijen, 3 verwijderd");
  // A var that is not a count is passed as a string and comes through ungrouped.
  expect(t("rows_kept", "en", { kept: "2024", deleted: 3 })).toBe("2024 rows, 3 removed");
});

test("every Dutch string is formal (u/uw), as the desktop consent screen is", () => {
  const informal: string[] = [];
  for (const key in T) {
    // Word-boundary match so "Kies", "rijen" and the like are left alone.
    if (/\b(je|jij|jouw)\b/i.test(T[key].nl)) informal.push(key);
  }
  expect(informal).toEqual([]);
});

test("no button-naming string still says Donate", () => {
  // The confirm screen's buttons read "share" since the screen was mirrored on
  // the desktop's; only intro_title still frames the study as a donation.
  for (const key of ["intro_body", "proceed", "all_checked", "confirm_title", "confirm_body", "donate", "decline"]) {
    expect(T[key].en.toLowerCase()).not.toContain("donat");
    expect(T[key].nl.toLowerCase()).not.toContain("doneer");
    expect(T[key].nl.toLowerCase()).not.toContain("donatie");
  }
  expect(T.intro_title.en).toBe("Donate your TikTok data");
});
