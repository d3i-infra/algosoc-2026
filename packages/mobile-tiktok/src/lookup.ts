export type Key = string | string[];

export function isRecord(v: unknown): v is { [k: string]: unknown } {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function get(d: unknown, ...keys: Key[]): unknown {
  let node: unknown = d;
  for (const key of keys) {
    if (!isRecord(node)) return undefined;
    if (Array.isArray(key)) {
      let found = false;
      for (const k of key) {
        if (Object.prototype.hasOwnProperty.call(node, k)) { node = node[k]; found = true; break; }
      }
      if (!found) return undefined;
    } else {
      node = Object.prototype.hasOwnProperty.call(node, key) ? node[key] : undefined;
    }
  }
  return node;
}

export function getFirst(d: unknown, ...paths: Key[][]): unknown {
  for (const path of paths) {
    const node = get(d, ...path);
    if (node !== undefined && node !== null) return node;
  }
  return undefined;
}

export function itemGet(item: unknown, ...keys: string[]): unknown {
  if (!isRecord(item)) throw new TypeError("item is not a record");
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(item, key)) return item[key];
    const lower = key.toLowerCase();
    if (Object.prototype.hasOwnProperty.call(item, lower)) return item[lower];
  }
  return "";
}

// The desktop consent form reads df.to_json() with JSON.parse and stringifies
// every cell with String(). Reproduce that: null/undefined -> "null",
// arrays join with ",", numbers via String, everything else via String.
export function cellText(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (Array.isArray(value)) return value.map(cellText).join(",");
  return String(value);
}
