export type Locale = "en" | "nl";

export const T: { [key: string]: { en: string; nl: string } } = {
  intro_title: { en: "Donate your TikTok data", nl: "Doneer je TikTok-gegevens" },
  intro_body: { en: "Choose the file TikTok sent you. Nothing is sent until you review it and press Donate.", nl: "Kies het bestand dat TikTok je heeft gestuurd. Er wordt niets verstuurd totdat je het hebt bekeken en op Doneren drukt." },
  choose_file: { en: "Choose file", nl: "Bestand kiezen" },
  working: { en: "Reading your file…", nl: "Je bestand wordt gelezen…" },
  retry_too_large: { en: "This file is too large to open on this device.", nl: "Dit bestand is te groot om op dit apparaat te openen." },
  retry_not_tiktok: { en: "This does not look like a TikTok export. Choose the zip file TikTok sent you.", nl: "Dit lijkt geen TikTok-export. Kies het zip-bestand dat TikTok je heeft gestuurd." },
  retry_unreadable: { en: "The file could not be read. Try downloading it again.", nl: "Het bestand kon niet worden gelezen. Probeer het opnieuw te downloaden." },
  try_again: { en: "Choose another file", nl: "Ander bestand kiezen" },
  stop: { en: "Stop", nl: "Stoppen" },
  tables_title: { en: "Your TikTok data", nl: "Je TikTok-gegevens" },
  tables_body: { en: "Look through each table. Tick the rows you want to remove, then press Remove selected. Tap a row to read it in full. Only what is left is donated.", nl: "Bekijk elke tabel. Vink de rijen aan die je wilt verwijderen en druk op Geselecteerde verwijderen. Tik op een rij om die volledig te lezen. Alleen wat overblijft wordt gedoneerd." },
  search: { en: "Search this table", nl: "Zoek in deze tabel" },
  rows_kept: { en: "{kept} rows, {deleted} removed", nl: "{kept} rijen, {deleted} verwijderd" },
  remove_matches: { en: "Remove all {n} matching rows", nl: "Alle {n} gevonden rijen verwijderen" },
  remove_selected: { en: "Remove selected ({n})", nl: "Geselecteerde verwijderen ({n})" },
  page_label: { en: "Page {x} of {y}", nl: "Pagina {x} van {y}" },
  prev_page: { en: "Previous", nl: "Vorige" },
  next_page: { en: "Next", nl: "Volgende" },
  jump_month: { en: "Jump to month", nl: "Ga naar maand" },
  confirm_remove: { en: "Remove {n} rows?", nl: "{n} rijen verwijderen?" },
  undo: { en: "Undo", nl: "Ongedaan maken" },
  no_rows: { en: "No rows to show.", nl: "Geen rijen om te tonen." },
  proceed: { en: "To donation summary", nl: "Naar het overzicht" },
  next_table: { en: "Next table", nl: "Volgende tabel" },
  back: { en: "Back", nl: "Terug" },
  confirm_title: { en: "Ready to donate?", nl: "Klaar om te doneren?" },
  confirm_body: { en: "These tables will be sent to the researchers. If you decline, only your decision is recorded.", nl: "Deze tabellen worden naar de onderzoekers gestuurd. Als je weigert, wordt alleen je beslissing vastgelegd." },
  donate: { en: "Donate", nl: "Doneren" },
  decline: { en: "Do not donate", nl: "Niet doneren" },
  sending: { en: "Sending…", nl: "Versturen…" },
  done_title: { en: "Thank you", nl: "Bedankt" },
  done_body: { en: "Your data has been received.", nl: "Je gegevens zijn ontvangen." },
  declined_body: { en: "Your decision has been recorded.", nl: "Je beslissing is vastgelegd." },
  failed_title: { en: "Sending failed", nl: "Versturen mislukt" },
  failed_body: { en: "Your data could not be sent. Check your connection and try again.", nl: "Je gegevens konden niet worden verstuurd. Controleer je verbinding en probeer het opnieuw." },
  retry_send: { en: "Try again", nl: "Opnieuw proberen" },
  error_title: { en: "Something went wrong", nl: "Er is iets misgegaan" },
  error_body: { en: "The file could not be processed on this device. You can report this so we can fix it. The report contains no data from your file.", nl: "Het bestand kon niet worden verwerkt op dit apparaat. Je kunt dit melden zodat we het kunnen oplossen. De melding bevat geen gegevens uit je bestand." },
  report: { en: "Report error", nl: "Fout melden" },
  skip: { en: "Skip", nl: "Overslaan" },
  incomplete_title: { en: "Task not completed", nl: "Taak niet voltooid" },
  incomplete_body: { en: "The task was not completed. You can close this page, or open the link again to try once more.", nl: "De taak is niet voltooid. Je kunt deze pagina sluiten, of de link opnieuw openen om het nog eens te proberen." },
};

// Every count shown to the participant is grouped by locale (200000 ->
// "200,000" / "200.000"); Safari 12 supports locale-aware toLocaleString, but
// a plain digit string is a safe fallback if a runtime lacks the data for it.
export function formatCount(n: number, locale: Locale): string {
  try {
    return n.toLocaleString(locale === "nl" ? "nl-NL" : "en-GB");
  } catch (_) {
    return String(n);
  }
}

// Every numeric var passed through here is treated as a count and grouped by
// locale via formatCount. All of today's numeric vars (rows_kept, the remove
// buttons, page_label) are counts; a var that is not one (a year, an id) must
// be passed as a string, or it will be silently grouped too.
export function t(key: string, locale: Locale, vars?: { [k: string]: string | number }): string {
  const entry = T[key];
  let s = entry ? entry[locale] || entry.en : key;
  if (vars) for (const k in vars) {
    const v = vars[k];
    s = s.split("{" + k + "}").join(typeof v === "number" ? formatCount(v, locale) : String(v));
  }
  return s;
}
