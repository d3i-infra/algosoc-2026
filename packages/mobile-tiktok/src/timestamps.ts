export interface ErrorCounter { add(key: string): void }

const NAMED_UTC = /[\s_]+(?:UTC|GMT)$/i;
// Python datetime.fromisoformat forms TikTok data uses: date only, date + time,
// optional fraction, optional Z or +HH:MM / -HH:MM / +HHMM.
const ISO = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?(Z|[+-]\d{2}:?\d{2})?$/i;

function lastSundayUtc(year: number, month0: number): number {
  const lastDay = new Date(Date.UTC(year, month0 + 1, 0));
  const day = lastDay.getUTCDate() - lastDay.getUTCDay();
  return Date.UTC(year, month0, day, 1, 0, 0);
}

export function amsterdamOffsetMinutes(utcMillis: number): number {
  const year = new Date(utcMillis).getUTCFullYear();
  const start = lastSundayUtc(year, 2);   // last Sunday of March, 01:00 UTC
  const end = lastSundayUtc(year, 9);     // last Sunday of October, 01:00 UTC
  return utcMillis >= start && utcMillis < end ? 120 : 60;
}

function pad(n: number): string { return n < 10 ? "0" + n : String(n); }

export function utcTimestampToDatetimeString(ts: unknown, errors: ErrorCounter): string {
  if (typeof ts !== "string" || ts === "") return "";
  const text = ts.trim().replace(NAMED_UTC, "");
  const m = ISO.exec(text);
  if (!m) { errors.add("TimestampParseError"); return ts; }
  const year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
  const hour = m[4] ? Number(m[4]) : 0, minute = m[5] ? Number(m[5]) : 0, second = m[6] ? Number(m[6]) : 0;
  let millis = Date.UTC(year, month - 1, day, hour, minute, second);
  if (isNaN(millis) || month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 59) {
    errors.add("TimestampParseError"); return ts;
  }
  // Date.UTC silently rolls a calendar-invalid date (Feb 30, Apr 31, day 0)
  // into the next/previous month instead of failing, unlike Python's
  // datetime.fromisoformat. Reject it the same way Python does by checking
  // the components round-trip.
  const rebuilt = new Date(millis);
  if (rebuilt.getUTCFullYear() !== year || rebuilt.getUTCMonth() !== month - 1 || rebuilt.getUTCDate() !== day) {
    errors.add("TimestampParseError"); return ts;
  }
  const zone = m[8];
  if (zone && zone.toUpperCase() !== "Z") {
    const sign = zone.charAt(0) === "-" ? -1 : 1;
    const digits = zone.slice(1).replace(":", "");
    const offset = sign * (Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2, 4)));
    millis -= offset * 60000;
  }
  const local = new Date(millis + amsterdamOffsetMinutes(millis) * 60000);
  return local.getUTCFullYear() + "-" + pad(local.getUTCMonth() + 1) + "-" + pad(local.getUTCDate()) + " " +
    pad(local.getUTCHours()) + ":" + pad(local.getUTCMinutes()) + ":" + pad(local.getUTCSeconds());
}
