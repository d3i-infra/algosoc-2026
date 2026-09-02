import {
  DonateButtons,
  BodyLarge,
  ReactFactoryContext,
} from "@eyra/feldspar"
import TextBundle from "@eyra/feldspar"
import { resolveText } from "../../locale/text"
import { 
    TableWithContext,
    TableContext,
    PropsUITable,
    PropsUITableBody,
    PropsUITableHead,
    PropsUIPromptConsentFormViz,
    PropsUIPromptConsentFormTableViz,
    PropsUITableRow,
} from "./types"
import { useCallback, useEffect, useMemo, useRef, useState, ReactElement } from "react"
import _ from "lodash"
import { TableContainer } from "./table_container"
import { TableSelector } from "./table_selector"

type Props = PropsUIPromptConsentFormViz & ReactFactoryContext

export const ConsentFormViz = (props: Props): ReactElement => {
  function rowCell(dataFrame: any, column: string, row: number): string {
    const text = String(dataFrame[column][`${row}`])
    return text
  }

  function columnNames(dataFrame: any): string[] {
    return Object.keys(dataFrame)
  }

  function columnCount(dataFrame: any): number {
    return columnNames(dataFrame).length
  }

  function rowCount(dataFrame: any): number {
    if (columnCount(dataFrame) === 0) {
      return 0
    } else {
      const firstColumn = dataFrame[columnNames(dataFrame)[0]]
      return Object.keys(firstColumn).length - 1
    }
  }

  function rows(data: any): PropsUITableRow[] {
    const result: PropsUITableRow[] = []
    const n = rowCount(data)
    for (let row = 0; row <= n; row++) {
      const id = `${row}`
      const cells = columnNames(data).map((column: string) => rowCell(data, column, row))
      result.push({ id, cells })
    }
    return result
  }

  function parseTables(tablesData: PropsUIPromptConsentFormTableViz[]): Array<PropsUITable & TableContext> {
    return tablesData.map((table) => parseTable(table))
  }

  function parseTable(tableData: PropsUIPromptConsentFormTableViz): PropsUITable & TableContext {
    const id = tableData.id
    const title = resolveText(tableData.title, props.locale)
    const description =
      tableData.description !== undefined ? resolveText(tableData.description, props.locale) : ""
    const deletedRowCount = 0
    const dataFrame = loadDataFrame(tableData.data_frame)
    const headCells = columnNames(dataFrame).map((column: string) => column)
    const head: PropsUITableHead = {
      cells: headCells,
    }
    const body: PropsUITableBody = {
      rows: rows(dataFrame),
    }

    // Translate column headers if provided. The headers dict maps DataFrame
    // column names to Translatable objects. We resolve them to the current
    // locale for display, while head.cells retains the raw DataFrame column
    // names for visualization data lookups.
    let translatedHeaders: Record<string, string> | undefined
    if (tableData.headers != null) {
      translatedHeaders = {}
      for (const [column, text] of Object.entries(tableData.headers)) {
        translatedHeaders[column] = resolveText(text, props.locale)
      }
    }

    return {
      __type__: "PropsUITable",
      id,
      head,
      body,
      title,
      description,
      deletedRowCount,
      annotations: [],
      originalBody: body,
      deletedRows: [],
      visualizations: tableData.visualizations,
      headers: translatedHeaders,
      folded: tableData.folded || false,
      deleteOption: tableData.delete_option,
    }
  }

  const [tables, setTables] = useState<TableWithContext[]>(() => parseTables(props.tables))
  const { locale, resolve } = props
  const { description, shareAllNote } = prepareCopy(props)
  const [selectedTableId, setSelectedTableId] = useState<string>("")
  // The state initializer above already parsed props.tables; only re-parse
  // when the host actually sends new tables (issue #122 double parse).
  const parsedTables = useRef(props.tables)

  useEffect(() => {
    if (parsedTables.current === props.tables) return
    parsedTables.current = props.tables
    setTables(parseTables(props.tables))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- PENDING_ISSUES "lint hygiene" entry 2026-08-26: consent_form_viz re-parse effect intentionally omits `parseTables` from deps. parseTables is a plain closure re-created every render, so listing it would make the dependency "changed" on every render regardless of whether props.tables actually changed; the effect's own ref-comparison guard (not this array) is what enforces ADR-0031's parse-once contract (issue #122 double parse), and widening this dependency array is exactly the kind of edit that has previously broken that contract by accident. A real fix would hoist parseTables/parseTable out of the component (or wrap them in useCallback keyed only on props.locale) so the function identity is stable and can be listed honestly.
  }, [props.tables])

  // Study UI: one table on screen at a time, in title order. Only the display
  // is scoped — `tables` (and so the donated payload) always holds every table.
  const sortedTables = useMemo(
    () => [...tables].sort((a, b) => a.title.localeCompare(b.title, locale)),
    [tables, locale]
  )

  // Falling back to the first table keeps the selection valid when the tables
  // change (e.g. on a new donation) without needing an extra effect.
  const selectedTable = useMemo(
    () => sortedTables.find((table) => table.id === selectedTableId) ?? sortedTables[0],
    [sortedTables, selectedTableId]
  )

  const updateTable = useCallback((tableId: string, table: TableWithContext) => {
    setTables((tables) => {
      const index = tables.findIndex((table) => table.id === tableId)
      if (index === -1) return tables

      const newTables = [...tables]
      newTables[index] = table
      return newTables
    })
  }, [])

  function handleDonate(): void {
    const value = serializeConsentData()
    resolve?.({ __type__: "PayloadJSON", "value": value })
  }

  function handleCancel(): void {
    resolve?.({ __type__: "PayloadFalse", value: false })
  }

  function serializeConsentData(): string {
    const array = serializeTables()
    return JSON.stringify(array)
  }

  function serializeTables(): any[] {
    return tables.map((table) => serializeTable(table))
  }


  function serializeTable({ id, head, body: { rows }, deletedRowCount }: TableWithContext): any {
    const data = rows.map((row) => serializeRow(row, head))
    return { [id]: data, "deleted row count": deletedRowCount.toString() }
  }

  function serializeRow(row: PropsUITableRow, head: PropsUITableHead): any {
    const keys = head.cells.map((cell) => cell)
    const values = row.cells.map((cell) => cell)
    return _.fromPairs(_.zip(keys, values))
  }

  return (
    <>
      <div className="max-w-3xl">
        {description.split("\n").map((line, index) => (
          <BodyLarge key={"description" + String(index)} text={line} />
        ))}
      </div>
      <div className="flex flex-col gap-16 w-full">
        <div className="grid gap-4 max-w-full">
          {selectedTable != null && (
            <>
              {/* A single table needs no selector (and its copy would read
                  "divided over 1 tables"); the e2e specs also find that
                  table's title by non-exact text, which an option label
                  repeating the title would make ambiguous. */}
              {sortedTables.length > 1 && (
                <TableSelector
                  tables={sortedTables}
                  selectedId={selectedTable.id}
                  onSelect={setSelectedTableId}
                  locale={locale}
                />
              )}
              {/* Keyed on the table id so switching unmounts the previous
                  table: its figures, and any visualization computation they
                  have in flight, are torn down instead of every table's
                  figures staying mounted at once. */}
              <TableContainer
                key={selectedTable.id}
                id={selectedTable.id}
                table={selectedTable}
                updateTable={updateTable}
                locale={locale}
              />
            </>
          )}
        </div>
        {/* Only one table is on screen, so spell out that sharing covers all of them. */}
        {sortedTables.length > 1 && (
          <BodyLarge
            margin=""
            text={shareAllNote.replace("{n}", sortedTables.length.toLocaleString(locale, { useGrouping: true }))}
          />
        )}
        <DonateButtons
          onDonate={handleDonate}
          onCancel={handleCancel}
          locale={locale}
          donateQuestion={props.donateQuestion ?? defaultDonateQuestionLabel}
          donateButton={props.donateButton ?? defaultDonateButtonLabel}
        />
      </div>
    </>
  )
}

interface Copy {
  description: string
  shareAllNote: string
}

function prepareCopy({ description, locale }: Props): Copy {
  return {
    description: resolveText(description ?? defaultDescription, locale),
    shareAllNote: resolveText(defaultShareAllNote, locale),
  }
}

function loadDataFrame(dataFrame: any) {
  if (typeof dataFrame === "string") {
      return JSON.parse(dataFrame)
  } 
  return dataFrame;
}

const defaultDonateQuestionLabel = new TextBundle()
  .add('en', 'Do you want to share the above data?')
  .add('de', 'Möchten Sie die oben genannten Daten teilen?')
  .add('nl', 'Wilt u de bovenstaande gegevens delen?')
  .add('it', 'Vuole condividere i dati sopra riportati?')
  .add('es', '¿Desea compartir los datos anteriores?')

const defaultDonateButtonLabel = new TextBundle()
  .add('en', 'Yes, share for research')
  .add('de', 'Ja, für Forschung teilen')
  .add('nl', 'Ja, deel voor onderzoek')
  .add('it', 'Sì, condividi per la ricerca')
  .add('es', 'Sí, compartir para la investigación')

const defaultShareAllNote = new TextBundle()
  .add('en', 'Sharing covers all {n} tables, also the ones you have not opened.')
  .add('nl', 'U deelt alle {n} tabellen, ook de tabellen die u niet heeft geopend.')
  .add('de', 'Geteilt werden alle {n} Tabellen, auch die, die Sie nicht geöffnet haben.')
  .add('it', 'La condivisione riguarda tutte le {n} tabelle, anche quelle che non ha aperto.')
  .add('es', 'Se comparten las {n} tablas, también las que no ha abierto.')

const defaultDescription = new TextBundle()
  .add('en', 'Determine whether you would like to share the data below. Carefully check the data and adjust when required. With your contribution, you help the previously described research. Thank you in advance.')
  .add('de', 'Legen Sie fest, ob Sie die untenstehenden Daten teilen möchten. Überprüfen Sie die Daten sorgfältig und passen Sie sie bei Bedarf an. Mit Ihrem Beitrag helfen Sie der zuvor beschriebenen Forschung. Vielen Dank im Voraus.')
  .add('nl', 'Bepaal of u de onderstaande gegevens wilt delen. Bekijk de gegevens zorgvuldig en pas zo nodig aan. Met uw bijdrage helpt u het eerder beschreven onderzoek. Alvast hartelijk dank.')
  .add('it', 'Decida se desidera condividere i dati riportati di seguito. Controlli attentamente i dati e li modifichi se necessario. Con il suo contributo aiuta la ricerca descritta in precedenza. Grazie in anticipo.')
  .add('es', 'Decida si desea compartir los datos que aparecen a continuación. Revise los datos con atención y modifíquelos si es necesario. Con su contribución ayuda a la investigación descrita anteriormente. Muchas gracias de antemano.')

