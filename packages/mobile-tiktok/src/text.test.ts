import { formatCount, t } from "./text";

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
  expect(t("page_label", "en", { x: 1, y: 1 })).toBe("Page 1 of 1");
});
