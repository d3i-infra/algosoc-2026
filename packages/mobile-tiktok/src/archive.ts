import { unzipSync, strFromU8 } from "fflate";

export type ArchiveErrorKind = "too_large" | "not_tiktok" | "unreadable";
export class ArchiveError extends Error {
  kind: ArchiveErrorKind;
  constructor(kind: ArchiveErrorKind) {
    super(kind);
    this.kind = kind;
    Object.setPrototypeOf(this, ArchiveError.prototype);
  }
}

export type Language = "nl" | "en";
export type Export =
  | { kind: "json"; data: unknown }
  | { kind: "txt"; language: Language; files: { [basename: string]: string } };

export const MAX_FILE_BYTES = 50 * 1024 * 1024;
export const MAX_MEMBER_BYTES = 100 * 1024 * 1024;

const JSON_FILES = ["user_data_tiktok.json", "user_data.json"];

// Basenames the 13 extractors read, per language. Order does not matter.
// Profile files carry the username for redaction. Mirrors the filenames in
// packages/python/port/platforms/tiktok.py per extractor.
export const TXT_FILES: { nl: string[]; en: string[] } = {
  nl: [
    "Samenvatting van activiteit.txt", "Instellingen.txt", "Kijkgeschiedenis.txt",
    "Favoriete video's.txt", "Volger.txt", "Volgend.txt", "Hashtag.txt", "Likelijst.txt",
    "Zoekopdrachten.txt", "Geschiedenis delen.txt", "Reacties.txt",
    "Activiteit buiten TikTok.txt", "Advertentie-interesses.txt", "Profielinformatie.txt",
  ],
  en: [
    "Activity Summary.txt", "Settings.txt", "Watch History.txt", "Favorite Videos.txt",
    "Follower.txt", "Following.txt", "Hashtag.txt", "Like List.txt", "Searches.txt",
    "Share History.txt", "Comments.txt", "Off-TikTok Activities.txt", "Ad Interests.txt",
    "Profile Information.txt",
  ],
};

// Filenames that identify a language even when the wanted ones are absent.
// Taken from DDP_CATEGORIES known_files in tiktok.py; a handful is enough.
const NL_MARKERS = ["Kijkgeschiedenis.txt", "Zoekopdrachten.txt", "Instellingen.txt", "Profielinformatie.txt", "Reacties.txt", "Likelijst.txt", "Volger.txt", "Volgend.txt", "Samenvatting van activiteit.txt"];
const EN_MARKERS = ["Watch History.txt", "Searches.txt", "Settings.txt", "Profile Information.txt", "Comments.txt", "Like List.txt", "Follower.txt", "Following.txt", "Activity Summary.txt"];

function basename(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}

// Python resolve_member: exact match, else exactly one "/<name>" suffix match.
function resolve(names: string[], wanted: string): string | null {
  if (names.indexOf(wanted) >= 0) return wanted;
  const suffix = "/" + wanted;
  const matches = names.filter((n) => n.length > suffix.length && n.slice(-suffix.length) === suffix);
  return matches.length === 1 ? matches[0] : null;
}

export function readFile(file: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(new ArchiveError("unreadable"));
    reader.readAsArrayBuffer(file);
  });
}

export function openExport(bytes: Uint8Array, maxMemberBytes: number = MAX_MEMBER_BYTES): Export {
  // First pass: names only. fflate's filter sees every entry; returning false
  // skips inflation. We record the names and inflate nothing.
  const names: string[] = [];
  const sizes: { [name: string]: number } = {};
  try {
    unzipSync(bytes, {
      filter: (f) => { names.push(f.name); sizes[f.name] = f.originalSize; return false; },
    });
  } catch (_) {
    throw new ArchiveError("unreadable");
  }
  if (names.length === 0) throw new ArchiveError("not_tiktok");

  // JSON export?
  for (const jsonName of JSON_FILES) {
    const member = resolve(names, jsonName);
    if (member) {
      if (sizes[member] > maxMemberBytes) throw new ArchiveError("too_large");
      const one = inflate(bytes, [member]);
      let data: unknown;
      try { data = JSON.parse(strFromU8(one[member])); } catch (_) { throw new ArchiveError("unreadable"); }
      return { kind: "json", data };
    }
  }

  // TXT export? Language from marker files.
  const bases = names.map(basename);
  const has = (list: string[]) => list.some((m) => bases.indexOf(m) >= 0);
  let language: Language | null = null;
  if (has(NL_MARKERS)) language = "nl";
  else if (has(EN_MARKERS)) language = "en";
  if (!language) throw new ArchiveError("not_tiktok");

  const wantedMembers: string[] = [];
  const byBase: { [base: string]: string } = {};
  for (const base of TXT_FILES[language]) {
    const member = resolve(names, base);
    if (!member) continue;
    if (sizes[member] > maxMemberBytes) throw new ArchiveError("too_large");
    wantedMembers.push(member);
    byBase[base] = member;
  }
  const inflated = inflate(bytes, wantedMembers);
  const files: { [basename: string]: string } = {};
  for (const base in byBase) files[base] = strFromU8(inflated[byBase[base]]);
  return { kind: "txt", language, files };
}

function inflate(bytes: Uint8Array, members: string[]): { [name: string]: Uint8Array } {
  try {
    return unzipSync(bytes, { filter: (f) => members.indexOf(f.name) >= 0 });
  } catch (_) {
    throw new ArchiveError("unreadable");
  }
}

export function loadExport(file: File): Promise<Export> {
  if (file.size > MAX_FILE_BYTES) return Promise.reject(new ArchiveError("too_large"));
  return readFile(file).then((buf) => openExport(new Uint8Array(buf)));
}
