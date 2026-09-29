export type Locale = "en" | "nl";

// Dutch is formal throughout (u/uw), matching the desktop consent screen this
// task sits beside: a participant may meet either surface in the same study.
// Where a string names a button, it says "share", not "donate" - no button has
// said Donate since the screen was mirrored on the desktop's.
export const T: { [key: string]: { en: string; nl: string } } = {
  intro_title: { en: "Donate your TikTok data", nl: "Doneer uw TikTok-gegevens" },
  intro_body: { en: "Choose the file TikTok sent you. Nothing is sent until you have reviewed it and pressed \"Yes, share for research\".", nl: "Kies het bestand dat TikTok u heeft gestuurd. Er wordt niets verstuurd totdat u het hebt bekeken en op 'Ja, deel voor onderzoek' klikt." },
  choose_file: { en: "Choose file", nl: "Bestand kiezen" },
  working: { en: "Reading your file…", nl: "Uw bestand wordt gelezen…" },
  retry_too_large: { en: "This file is too large to open on this device.", nl: "Dit bestand is te groot om op dit apparaat te openen." },
  retry_not_tiktok: { en: "This does not look like a TikTok export. Choose the zip file TikTok sent you.", nl: "Dit lijkt geen TikTok-export. Kies het zip-bestand dat TikTok u heeft gestuurd." },
  retry_unreadable: { en: "The file could not be read. Try downloading it again.", nl: "Het bestand kon niet worden gelezen. Probeer het opnieuw te downloaden." },
  try_again: { en: "Choose another file", nl: "Ander bestand kiezen" },
  stop: { en: "Stop", nl: "Stoppen" },
  tables_title: { en: "Your TikTok data", nl: "Uw TikTok-gegevens" },
  tables_body: { en: "Check each table. Tick rows to remove them. Tap a row to read it in full.", nl: "Bekijk elke tabel. Vink rijen aan om ze te verwijderen. Tik op een rij om die volledig te lezen." },
  // The table selector, verbatim from the desktop's table_selector.tsx.
  selector_heading: { en: "Your data is divided over {n} tables", nl: "Uw gegevens zijn verdeeld over {n} tabellen" },
  selector_explanation: { en: "Only one table is shown at a time. Use the menu below to view the others. Please check them all before sharing.", nl: "Er wordt steeds één tabel getoond. Gebruik het menu hieronder om de andere tabellen te bekijken. Bekijk ze alstublieft allemaal voordat u deelt." },
  selector_label: { en: "Select a table", nl: "Kies een tabel" },
  selector_position: { en: "{i} of {n}", nl: "{i} van {n}" },
  prev_table: { en: "Previous table", nl: "Vorige tabel" },
  next_table: { en: "Next table", nl: "Volgende tabel" },
  search: { en: "Search", nl: "Zoeken" },
  // The summary line, verbatim from the desktop's table_items.tsx.
  row: { en: "row", nl: "rij" },
  rows: { en: "rows", nl: "rijen" },
  columns: { en: "columns", nl: "kolommen" },
  deleted: { en: "deleted", nl: "verwijderd" },
  no_data: { en: "no data", nl: "geen data" },
  rows_kept: { en: "{kept} rows, {deleted} removed", nl: "{kept} rijen, {deleted} verwijderd" },
  select_all: { en: "Select all rows", nl: "Alle rijen selecteren" },
  // The paging arrows carry no text, and here they are the only way through a
  // long table, so each one names itself for VoiceOver.
  first_page: { en: "First page", nl: "Eerste pagina" },
  prev_page: { en: "Previous page", nl: "Vorige pagina" },
  next_page: { en: "Next page", nl: "Volgende pagina" },
  last_page: { en: "Last page", nl: "Laatste pagina" },
  delete: { en: "Delete {n}", nl: "Verwijder {n}" },
  undo: { en: "Undo", nl: "Herstel" },
  share_all: { en: "Sharing covers all {n} tables, also the ones you have not opened.", nl: "U deelt alle {n} tabellen, ook de tabellen die u niet heeft geopend." },
  all_checked: { en: "Checked everything? Press \"Show summary before sharing\" to continue.", nl: "Alles bekeken? Klik op 'Toon samenvatting voor delen' om verder te gaan." },
  proceed: { en: "Show summary before sharing", nl: "Toon samenvatting voor delen" },
  back: { en: "Back", nl: "Terug" },
  confirm_title: { en: "Ready to share?", nl: "Klaar om te delen?" },
  confirm_body: { en: "These tables will be sent to the researchers. If you say no, only your decision is recorded.", nl: "Deze tabellen worden naar de onderzoekers gestuurd. Als u nee zegt, wordt alleen uw beslissing vastgelegd." },
  donate_question: { en: "Do you want to share the above data?", nl: "Wilt u de bovenstaande gegevens delen?" },
  donate: { en: "Yes, share for research", nl: "Ja, deel voor onderzoek" },
  decline: { en: "No, do not share", nl: "Nee, niet delen" },
  sending: { en: "Sending…", nl: "Versturen…" },
  done_title: { en: "Thank you", nl: "Bedankt" },
  done_body: { en: "Your data has been received.", nl: "Uw gegevens zijn ontvangen." },
  declined_body: { en: "Your decision has been recorded.", nl: "Uw beslissing is vastgelegd." },
  failed_title: { en: "Sending failed", nl: "Versturen mislukt" },
  failed_body: { en: "Your data could not be sent. Check your connection and try again.", nl: "Uw gegevens konden niet worden verstuurd. Controleer uw verbinding en probeer het opnieuw." },
  retry_send: { en: "Try again", nl: "Opnieuw proberen" },
  error_title: { en: "Something went wrong", nl: "Er is iets misgegaan" },
  error_body: { en: "The file could not be processed on this device. You can report this so we can fix it. The report contains no data from your file.", nl: "Het bestand kon niet worden verwerkt op dit apparaat. U kunt dit melden zodat we het kunnen oplossen. De melding bevat geen gegevens uit uw bestand." },
  report: { en: "Report error", nl: "Fout melden" },
  skip: { en: "Skip", nl: "Overslaan" },
  incomplete_title: { en: "Task not completed", nl: "Taak niet voltooid" },
  incomplete_body: { en: "The task was not completed. You can close this page, or open the link again to try once more.", nl: "De taak is niet voltooid. U kunt deze pagina sluiten, of de link opnieuw openen om het nog eens te proberen." },
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
// button) are counts; a var that is not one (a year, an id, a page number)
// must be passed as a string, or it will be silently grouped too.
export function t(key: string, locale: Locale, vars?: { [k: string]: string | number }): string {
  const entry = T[key];
  let s = entry ? entry[locale] || entry.en : key;
  if (vars) for (const k in vars) {
    const v = vars[k];
    s = s.split("{" + k + "}").join(typeof v === "number" ? formatCount(v, locale) : String(v));
  }
  return s;
}
