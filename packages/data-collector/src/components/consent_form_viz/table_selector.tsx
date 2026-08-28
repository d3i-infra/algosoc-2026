import { useMemo } from "react"
import { Translator } from "@eyra/feldspar"
import TextBundle from "@eyra/feldspar"
import { TableWithContext } from "./types"

interface Props {
  tables: TableWithContext[]
  selectedId: string
  onSelect: (tableId: string) => void
  locale: string
}

/**
 * Lets the participant page through the tables one at a time. Only the selected
 * table is mounted (see consent_form_viz), so this bar is the only place that
 * tells them how much data there is in total. That is why it repeats the count
 * in the heading, in the option labels and in the position indicator.
 */
export const TableSelector = ({ tables, selectedId, onSelect, locale }: Props): JSX.Element => {
  const text = useMemo(() => getTranslations(locale), [locale])

  const index = Math.max(
    0,
    tables.findIndex((table) => table.id === selectedId)
  )
  const total = tables.length
  const countLabel = total.toLocaleString(locale, { useGrouping: true })

  function optionLabel(table: TableWithContext): string {
    const rows = table.body.rows.length
    const rowsLabel = rows.toLocaleString(locale, { useGrouping: true })
    return `${table.title} (${rowsLabel} ${rows === 1 ? text.row : text.rows})`
  }

  function step(direction: number): void {
    const next = tables[index + direction]
    if (next !== undefined) onSelect(next.id)
  }

  return (
    <div className="flex flex-col gap-4 p-3 md:p-4 lg:p-6 bg-grey6 border-[0.2rem] border-grey4 rounded-lg">
      <div className="flex gap-3">
        <div className="text-primary shrink-0">{stackIcon}</div>
        <div className="flex flex-col gap-1">
          <div className="text-title6 font-label">{text.heading.replace("{n}", countLabel)}</div>
          <p className="text-base md:text-lg font-body max-w-2xl">
            {text.explanation.replace("{n}", countLabel)}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex flex-col gap-1 grow max-w-xl">
          <span className="text-title7 font-label">{text.label}</span>
          <div className="relative">
            <select
              className={`w-full appearance-none cursor-pointer text-grey1 font-body bg-white
              pl-3 pr-10 h-44px border-2 border-solid border-grey3 rounded-lg
              focus:outline-none focus:border-primary`}
              value={selectedId}
              onChange={(e) => onSelect(e.target.value)}
            >
              {tables.map((table) => (
                <option key={table.id} value={table.id}>
                  {optionLabel(table)}
                </option>
              ))}
            </select>
            <div className="absolute right-3 top-0 h-full flex items-center pointer-events-none text-primary">
              {chevronDownIcon}
            </div>
          </div>
        </label>

        <div className="flex items-center gap-2 self-end h-44px">
          <StepButton icon={chevronLeftIcon} label={text.previous} disabled={index === 0} onClick={() => step(-1)} />
          <div className="whitespace-nowrap text-title7 font-label px-1">
            {text.position.replace("{i}", String(index + 1)).replace("{n}", countLabel)}
          </div>
          <StepButton
            icon={chevronRightIcon}
            label={text.next}
            disabled={index === total - 1}
            onClick={() => step(1)}
          />
        </div>
      </div>
    </div>
  )
}

function StepButton({
  icon,
  label,
  disabled,
  onClick,
}: {
  icon: JSX.Element
  label: string
  disabled: boolean
  onClick: () => void
}): JSX.Element {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`flex items-center justify-center w-10 h-10 rounded-lg border-2 border-solid border-grey3 text-primary
      ${disabled ? "opacity-40 cursor-default" : "hover:border-primary"}`}
    >
      {icon}
    </button>
  )
}

const stackIcon = (
  <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="m3 12 9 4.5 9-4.5" />
    <path strokeLinecap="round" strokeLinejoin="round" d="m3 16.5 9 4.5 9-4.5" />
  </svg>
)

const chevronDownIcon = (
  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
  </svg>
)

const chevronLeftIcon = (
  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="m15 6-6 6 6 6" />
  </svg>
)

const chevronRightIcon = (
  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="m9 6 6 6-6 6" />
  </svg>
)

function getTranslations(locale: string): Record<string, string> {
  const translated: Record<string, string> = {}
  for (const [key, value] of Object.entries(translations)) {
    translated[key] = Translator.translate(value, locale)
  }
  return translated
}

const translations = {
  heading: new TextBundle()
    .add("en", "Your data is divided over {n} tables")
    .add("de", "Ihre Daten sind auf {n} Tabellen verteilt")
    .add("nl", "Uw gegevens zijn verdeeld over {n} tabellen"),
  explanation: new TextBundle()
    .add(
      "en",
      "Only one table is shown at a time. Use the menu below to view the others. Please check them all before sharing."
    )
    .add(
      "de",
      "Es wird jeweils nur eine Tabelle angezeigt. Über das Menü unten sehen Sie die übrigen. Bitte prüfen Sie alle, bevor Sie teilen."
    )
    .add(
      "nl",
      "Er wordt steeds één tabel getoond. Gebruik het menu hieronder om de andere tabellen te bekijken. Bekijk ze alstublieft allemaal voordat u deelt."
    ),
  label: new TextBundle()
    .add("en", "Select a table")
    .add("de", "Tabelle auswählen")
    .add("nl", "Kies een tabel"),
  position: new TextBundle()
    .add("en", "{i} of {n}")
    .add("de", "{i} von {n}")
    .add("nl", "{i} van {n}"),
  previous: new TextBundle().add("en", "Previous table").add("de", "Vorherige Tabelle").add("nl", "Vorige tabel"),
  next: new TextBundle().add("en", "Next table").add("de", "Nächste Tabelle").add("nl", "Volgende tabel"),
  row: new TextBundle().add("en", "row").add("de", "Zeile").add("nl", "rij"),
  rows: new TextBundle().add("en", "rows").add("de", "Zeilen").add("nl", "rijen"),
}
