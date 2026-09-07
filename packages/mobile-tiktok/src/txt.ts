export type TxtValue = string | number | null | string[];
export type TxtRecord = { [key: string]: TxtValue };
export type TxtNested = { [key: string]: TxtValue | TxtRecord };
export type TxtParsed = TxtRecord | TxtRecord[] | TxtNested | null;

const EMPTY_SENTINELS = [
  "dit gedeelte bevat geen gegevens",
  "er staan geen gegevens in dit gedeelte",
  "je hebt geen informatie over platforms van derden",
  "you have no data in this section",
];
const NULL_LIKE = ["n/a", "n.v.t.", "none"];

export function isEmptySentinel(line: string): boolean {
  return EMPTY_SENTINELS.indexOf(line.trim().toLowerCase()) >= 0;
}

export function parseValue(raw: string): TxtValue {
  const s = raw.trim();
  if (s === "[]") return [];
  if (s.length >= 2 && s.charAt(0) === "[" && s.charAt(s.length - 1) === "]") {
    const inner = s.slice(1, -1).trim();
    if (inner === "") return [];
    return inner.split(",").map((item) => item.trim());
  }
  if (NULL_LIKE.indexOf(s.toLowerCase()) >= 0) return null;
  if (/^[+-]?[0-9]+$/.test(s)) return Number(s);
  return s;
}

// Python str.partition(":"): key before the first colon, value after it.
function partition(line: string): [string, string] {
  const i = line.indexOf(":");
  return [line.slice(0, i).trim(), line.slice(i + 1)];
}

function splitIntoBlocks(lines: string[]): string[][] {
  const blocks: string[][] = [];
  let current: string[] = [];
  for (const line of lines) {
    if (line.trim() === "") {
      if (current.length) { blocks.push(current); current = []; }
    } else {
      current.push(line);
    }
  }
  if (current.length) blocks.push(current);
  return blocks;
}

function blockOnlyKv(block: string[]): boolean {
  return block.every((line) => line.indexOf(":") >= 0);
}

function parseKvBlock(block: string[]): TxtRecord {
  const result: TxtRecord = {};
  for (const line of block) {
    if (line.indexOf(":") < 0) continue;
    const [key, raw] = partition(line);
    result[key] = parseValue(raw);
  }
  return result;
}

function keySet(block: string[]): string {
  const keys = block.map((line) => partition(line)[0]);
  keys.sort();
  return keys.filter((k, i) => i === 0 || keys[i - 1] !== k).join("\u0000");
}

export function parseTikTokTxt(text: string): TxtParsed {
  const lines = text.split("\n").map((l) => (l.length && l.charAt(l.length - 1) === "\r" ? l.slice(0, -1) : l));
  while (lines.length && lines[lines.length - 1].trim() === "") lines.pop();
  if (lines.length === 0 || (lines.length === 1 && isEmptySentinel(lines[0]))) return null;

  const blocks = splitIntoBlocks(lines);
  if (blocks.length === 0) return null;

  if (blocks.length === 1 && blockOnlyKv(blocks[0])) return parseKvBlock(blocks[0]);

  if (blocks.length >= 2 && blockOnlyKv(blocks[0]) && blockOnlyKv(blocks[1])) {
    const keys0 = keySet(blocks[0]);
    if (keys0 === keySet(blocks[1])) {
      const records: TxtRecord[] = [];
      let complete = true;
      for (const blk of blocks) {
        if (blockOnlyKv(blk) && keySet(blk) === keys0) records.push(parseKvBlock(blk));
        else { complete = false; break; }
      }
      if (complete) return records;
    }
  }

  const result: TxtNested = {};
  for (const block of blocks) {
    let section: string | null = null;
    let start = 0;
    const first = block[0];
    if ((first.indexOf(":") < 0 || first.trim().slice(-1) === ":") && block.length > 1) {
      if (block[1].indexOf(":") >= 0 || isEmptySentinel(block[1])) {
        section = first.trim();
        result[section] = {};
        start = 1;
      }
    }
    for (const line of block.slice(start)) {
      if (line.indexOf(":") >= 0) {
        const [key, raw] = partition(line);
        const value = parseValue(raw);
        if (section !== null) (result[section] as TxtRecord)[key] = value;
        else result[key] = value;
      } else if (line.trim().length > 0 && !isEmptySentinel(line)) {
        section = line.trim();
        result[section] = {};
      }
    }
  }
  return result;
}
