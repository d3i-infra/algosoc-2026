import { utcTimestampToDatetimeString, amsterdamOffsetMinutes } from "./timestamps";

function counter() { const keys: string[] = []; return { keys, add: (k: string) => { keys.push(k); } }; }

test("bare UTC timestamp is written in Amsterdam time", () => {
  expect(utcTimestampToDatetimeString("2026-05-02 10:09:50", counter())).toBe("2026-05-02 12:09:50");
  expect(utcTimestampToDatetimeString("2026-01-15 23:30:00", counter())).toBe("2026-01-16 00:30:00");
});

test("named UTC or GMT suffix is stripped first", () => {
  expect(utcTimestampToDatetimeString("2026-05-02 10:09:50 UTC", counter())).toBe("2026-05-02 12:09:50");
  expect(utcTimestampToDatetimeString("2026-05-02 10:09:50_gmt", counter())).toBe("2026-05-02 12:09:50");
});

test("ISO forms with T, Z and offsets", () => {
  expect(utcTimestampToDatetimeString("2026-05-02T10:09:50Z", counter())).toBe("2026-05-02 12:09:50");
  expect(utcTimestampToDatetimeString("2026-05-02T10:09:50+02:00", counter())).toBe("2026-05-02 10:09:50");
  expect(utcTimestampToDatetimeString("2026-05-02T10:09:50.123456", counter())).toBe("2026-05-02 12:09:50");
  expect(utcTimestampToDatetimeString("2026-05-02", counter())).toBe("2026-05-02 02:00:00");
});

test("DST boundaries follow EU rules", () => {
  // 2026: DST starts Sun 29 March 01:00 UTC, ends Sun 25 October 01:00 UTC.
  expect(utcTimestampToDatetimeString("2026-03-29 00:59:59", counter())).toBe("2026-03-29 01:59:59");
  expect(utcTimestampToDatetimeString("2026-03-29 01:00:00", counter())).toBe("2026-03-29 03:00:00");
  expect(utcTimestampToDatetimeString("2026-10-25 00:59:59", counter())).toBe("2026-10-25 02:59:59");
  expect(utcTimestampToDatetimeString("2026-10-25 01:00:00", counter())).toBe("2026-10-25 02:00:00");
  expect(amsterdamOffsetMinutes(Date.UTC(2024, 6, 1))).toBe(120);
  expect(amsterdamOffsetMinutes(Date.UTC(2024, 0, 1))).toBe(60);
});

test("unparseable input is returned unchanged and counted", () => {
  const c = counter();
  expect(utcTimestampToDatetimeString("yesterday", c)).toBe("yesterday");
  expect(c.keys).toEqual(["TimestampParseError"]);

  const c2 = counter();
  expect(utcTimestampToDatetimeString("2026-02-30 10:00:00", c2)).toBe("2026-02-30 10:00:00");
  expect(c2.keys).toEqual(["TimestampParseError"]);

  const c3 = counter();
  expect(utcTimestampToDatetimeString("2026-04-31", c3)).toBe("2026-04-31");
  expect(c3.keys).toEqual(["TimestampParseError"]);
});

test("empty or non-string input is empty", () => {
  expect(utcTimestampToDatetimeString("", counter())).toBe("");
  expect(utcTimestampToDatetimeString(null, counter())).toBe("");
  expect(utcTimestampToDatetimeString(5, counter())).toBe("");
});
