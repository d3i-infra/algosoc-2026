import type { ReviewState } from "./review/state";

export const DECLINE_PAYLOAD = '{"status": "data_submission declined"}';

// Builds the JSON incrementally so the tables are never copied into a second
// object graph. Output is byte-identical to JSON.stringify of the equivalent
// structure: JSON.stringify is used for every key and cell.
export function serializePayload(state: ReviewState): string {
  const parts: string[] = ["["];
  for (let ti = 0; ti < state.tables.length; ti++) {
    const t = state.tables[ti];
    const keys = t.table.columns.map((c) => JSON.stringify(c) + ":");
    if (ti > 0) parts.push(",");
    parts.push("{", JSON.stringify(t.table.id), ":[");
    let first = true;
    const rows = t.table.rows;
    for (let i = 0; i < rows.length; i++) {
      if (t.deleted[i]) continue;
      if (!first) parts.push(",");
      first = false;
      parts.push("{");
      const row = rows[i];
      // A row with fewer cells than columns would emit `"Link":undefined` —
      // not JSON at all. Refuse instead: the controller's crash path turns this
      // into the error screen, never a corrupt donation.
      if (row.length < keys.length) throw new Error("payload_row_shape");
      for (let c = 0; c < keys.length; c++) {
        if (c > 0) parts.push(",");
        parts.push(keys[c], JSON.stringify(row[c]));
      }
      parts.push("}");
    }
    parts.push('],"deleted row count":', JSON.stringify(String(t.deletedCount)), "}");
  }
  parts.push("]");
  return parts.join("");
}
