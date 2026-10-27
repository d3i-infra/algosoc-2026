import _ from "lodash"
import { PropsUITableHead, PropsUITableRow, TableWithContext } from "./types"

// The donated payload: every non-deleted row of every table (ADR-0031), plus the
// participant's deletion count and the validation record Python attached to the
// consent prompt, written once per table beside that count.

export function serializeConsentData(
  tables: TableWithContext[],
  validation?: Record<string, string | number>
): string {
  const array = serializeTables(tables, validation)
  return JSON.stringify(array)
}

export function serializeTables(
  tables: TableWithContext[],
  validation?: Record<string, string | number>
): Array<Record<string, unknown>> {
  return tables.map((table) => serializeTable(table, validation))
}

export function serializeTable(
  { id, head, body: { rows }, deletedRowCount }: TableWithContext,
  validation?: Record<string, string | number>
): Record<string, unknown> {
  const data = rows.map((row) => serializeRow(row, head))
  const table: Record<string, unknown> = { [id]: data, "deleted row count": deletedRowCount.toString() }
  if (validation !== undefined) {
    table.validation = validation
  }
  return table
}

export function serializeRow(row: PropsUITableRow, head: PropsUITableHead): any {
  const keys = head.cells.map((cell) => cell)
  const values = row.cells.map((cell) => cell)
  return _.fromPairs(_.zip(keys, values))
}
