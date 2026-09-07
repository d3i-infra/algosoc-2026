# mobile-tiktok

A phone-only TikTok donation task for Next. It exists because the desktop task bundle
(React, Pyodide, and their dependencies) cannot be parsed by Safari 12, the last browser
an iPhone 6 can run, and the AlgoSoc panel includes participants whose only device is
such a phone. This package is a second Next task with the same donation payload, built
with no framework and no Python runtime, and it targets Safari 12 and newer.

Design: docs/superpowers/specs/2026-09-06-mobile-tiktok-design.md.
Rules it follows: docs/decisions/0041-*.md (flow rules) and docs/decisions/0003-*.md
(package boundaries).

## How it runs

Next loads the built `dist/` in an iframe, exactly as it loads the desktop bundle. The
app speaks the same host protocol (below), donates under the same key, and produces the
same payload bytes as the desktop flow for the same export and the same participant
choices.

The package imports nothing from `feldspar`, `data-collector`, or `python` at runtime.
Its one build-time dependency on the rest of the repo is
`packages/python/port/configs/tiktok_config.json`, which defines the tables, their ids,
titles, descriptions, headers, and extractor names for both flows.

The build runs `scripts/syntax-gate.sh` over the bundle and fails on anything Safari 12
cannot parse or run: optional chaining, nullish coalescing, `import.meta`, regex
lookbehind, BigInt literals, `String.replaceAll`, `Object.fromEntries`,
`Blob.arrayBuffer`, `queueMicrotask`, `structuredClone`, `ResizeObserver`,
`IntersectionObserver`. The CSS is Tailwind 3 with the feldspar preset; Tailwind 4 needs
Safari 16.4.

## Commands (from the repo root)

- `pnpm --filter @eyra/mobile-tiktok dev` starts a dev server with a fake host page at
  http://localhost:3100/fake-host.html that mirrors mono's iframe hook.
- `pnpm --filter @eyra/mobile-tiktok test` runs the unit tests and the parity tests.
- `pnpm --filter @eyra/mobile-tiktok typecheck` runs `tsc`.
- `pnpm --filter @eyra/mobile-tiktok build` writes `dist/` and runs the Safari 12 gate.
- `pnpm --filter @eyra/mobile-tiktok fixtures` regenerates the synthetic fixtures and
  the desktop extractor's expected output for them (needs the `packages/python` poetry
  environment).
- `pnpm --filter @eyra/mobile-tiktok run test:e2e --project=chromium` runs the Playwright
  flow tests against the fake host.

`release.sh` zips `dist/` alongside the platform bundle.

## Layout

| Module | Role |
|---|---|
| `src/archive.ts` | Opens the export zip with fflate, detects JSON or TXT and the language, inflates only the wanted members. |
| `src/txt.ts` | Port of the desktop TXT export parser. |
| `src/lookup.ts`, `src/timestamps.ts`, `src/redact.ts` | Nested lookup, timestamp conversion to Amsterdam time, email and own-username redaction. |
| `src/config.ts`, `src/extract.ts` | The shared table config and the thirteen extractors, ported from `platforms/tiktok.py`. |
| `src/review/state.ts` | Review state: deletions with undo, search, selection, pages of 50, month index. |
| `src/review/screens.ts`, `src/text.ts`, `src/styles.css` | Every screen as plain DOM, English and Dutch strings. |
| `src/payload.ts` | The donation payload in the desktop shape. |
| `src/host.ts` | The Next host protocol over `postMessage` and a `MessageChannel`. |
| `src/controller.ts`, `src/main.ts` | The participant flow and the entry point. |
| `fixtures/` | The synthetic fixture generator and its committed output. Real exports go in `fixtures/ddp/`, which git ignores. |
| `e2e/` | Playwright flows through the fake host. |

## The Next boundary

The app implements the protocol mono's `feldspar_app.js` hook expects, the same protocol
the fork's `feldspar` bridge implements for the desktop bundle. Nothing on the Next side
changes.

- On load the app posts `app-loaded` to the parent. The host answers with `live-init`,
  a locale, and a `MessageChannel` port. Mono creates a fresh channel on every
  `app-loaded`, so a second `live-init` replaces the port; any donation still waiting on
  the old port is failed so the participant sees Retry rather than a hang. This matches
  the desktop bridge's `updatePort`.
- The app replies `initialized` on the port at once. The desktop sends it only after
  Pyodide has started, which is what mono's spinner waits for.
- `resize` messages carry the height of the app root plus 48 px, posted after each
  render. The desktop uses a `ResizeObserver` on the document, which Safari 12 lacks.
  The root is measured rather than the document because inside an iframe the document
  is never shorter than the frame the host has already grown.
- Donations are `CommandSystemDonate` with the key `<session id>-tiktok`, where the
  session id is `String(Date.now())` as on the desktop, and the app waits for mono's
  `DonateSuccess` or `DonateError` reply. A declined consent donates the literal
  `{"status": "data_submission declined"}`.
- Logs are `CommandSystemLog` whose message is one of a fixed set of milestone names
  (`file_selected`, `archive_read`, `extracted`, `review_shown`, `consent_accepted`,
  `consent_declined`, `donate_started`, `donate_succeeded`, `donate_failed`,
  `error_shown`, `error_report_sent`, `error_report_skipped`, `exited`). No text
  derived from the export ever reaches the host.
- The exit is one `CommandSystemExit`, sent once: code 0 `completed` after a delivered
  donation or decline; 1 `error` after an error, whether or not a report was sent;
  3 `donation_failed` when the participant stops after a failed donation;
  4 `upload_rejected` when they stop on the invalid-file screen. Mono completes the task
  on 0 and keeps it pending otherwise.
- An error report, sent only when the participant chooses to, goes under the key
  `error-report` and contains the platform, a fixed error category, the app version, the
  user agent string, and a timestamp. It never contains exception text.

## Differences from the desktop flow

The parity tests in `src/parity.test.ts` hold the extractor to the desktop's output on
the synthetic fixtures, in both formats and both languages, row for row. Everything
below is either outside that comparison or a deliberate divergence.

### Reading the zip

The desktop reads the zip through a seekable adapter and never loads it whole. The
phone reads the file into memory and hands it to fflate, then lists member names
without inflating anything, and inflates only the JSON member or the named TXT files.
The file is capped at 50 MB and a member at 100 MB; the desktop caps are 2 GiB and
512 MB. Format detection checks for the JSON member by name, then decides the TXT
language from marker files; the desktop scores member names against its known-file
lists. Member resolution follows the desktop rule (exact path, else exactly one
path-boundary suffix match) but without the desktop's apostrophe-to-underscore retry
for Google Drive downloads. Failures are reported as one of three kinds, too large, not
a TikTok export, unreadable, each with its own message; the desktop has one generic
retry message.

### TXT parser

A line-for-line port. Known edge differences: the English "no data" sentinel matches on
the phone and never matches on the desktop, which stores it with a capital letter and
compares lower-cased; the phone parses ASCII integers only where Python's `int()`
accepts more, and a 19-digit integer would lose precision as a JavaScript number; a
byte-order mark at the start of a file is trimmed on the phone and kept on the desktop;
JavaScript orders integer-like object keys first.

### Lookup and cells

The three lookup helpers are ported directly. Own-property checks stand in for Python's
`in`. Cell text reproduces the visible result of the desktop's chain, pandas
`to_json` followed by `String()` in the consent screen: `null` becomes the text
"null", arrays join with commas. Pandas rounds floats to ten significant digits; the
phone would not, but no current table has a float column.

### Timestamps

The phone accepts the ISO forms TikTok writes (date, optional time with optional
seconds and fraction, optional Z or two-part offset); Python's `fromisoformat` accepts
more. Calendar-invalid dates are rejected as Python rejects them. Conversion to
Amsterdam time uses the current European daylight-saving rule in code rather than a
zone database; the two agree for every date since 1996.

### Extractor

The same loop over the same config, the same extractor names, empty tables dropped.
The desktop's two known bugs are reproduced so the payloads match: the ad-interests
table is always empty, and the settings extractor raises when the content-preferences
section is absent. The desktop sorts each dated table newest-first, but pandas keeps
the original index labels and the consent screen reads rows by label, so participants
see and donate export order on both sides; the phone does not sort. Extraction runs on
the main thread and yields to the browser between tables, where the desktop runs in a
worker. Extraction error counts stay internal on the phone; the desktop logs a
count-only summary to the host. Free-text columns (`Comment`, `SearchTerm`,
`SharedContent`) have email addresses replaced by `[email]` and the participant's own
username, when the export carries a profile, replaced by `[user]`; the desktop TikTok
flow does no redaction.

### Review and payload

Both sides keep the original rows and a set of deletions, count deleted rows, push one
undo entry per action, and offer removing every row a search matches. The phone's undo
is one stack across all tables; the desktop's is per table. The desktop has a select-all
over the filtered rows; the phone has per-row checkboxes on pages of 50. Search is a
case-insensitive substring test on every cell; the desktop builds a regular expression.
The phone shows one table at a time in config order; the desktop shows one table at a
time in title order. The payload is byte-identical to the desktop's: every table in
config order, every non-deleted row keyed by the raw column names, and a "deleted row
count" string per table, whatever the screen was showing.

### Flow

A clean export that yields no tables is an extraction failure on the phone (exit 1,
task pending); on the desktop it shows a no-data page and completes the task. A failed
donation offers Retry on the phone with the payload kept in memory; the desktop exits
after showing a failure page. The invalid-file screen offers Choose another file and
Stop, and Stop exits 4; the desktop's equivalent Continue exits 2. The tables screen
has Choose another file, which returns to the start with nothing kept; the desktop has
no equivalent once validation has passed. The error screen never shows exception text;
the desktop shows the traceback. English and Dutch only.

## Known limits

- Leaving the page (sleep, a tab or app switch) can make iOS discard it and reload it
  from scratch. The app keeps nothing between loads by design, so the participant
  starts over from the file picker; iOS gives the page no reliable signal that this
  happened, so there is no on-screen explanation.
- The 50 MB file cap follows from reading the zip into memory. Both TikTok formats are
  far below it for any export seen so far.
- The daylight-saving rule is fixed in code. A change to the European rule needs a code
  change here and a package update on the desktop.
- Playwright's WebKit cannot launch on the Arch development host; the flow tests run on
  Chromium there. Device behaviour is verified on the iPhone 6 itself.
