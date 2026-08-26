---
status: proposed
date: "2026-08-20"
tags:
    - ddp
    - locale
    - validation
source: Extending the Google Takeout flow beyond YouTube (2026-08-20)
category: Python architecture
applies_to:
    - packages/python/port/platforms/google.py
priority: default
companions:
    - packages/python/tests/test_google_paths.py
---

# Locale-aware path lookup for multi-source archives

## Decision

A platform whose DDP holds several sources in one archive owns its validation: it recognizes the archive, and determines its locale, by matching **paths** from a locale table it owns. It defines no `DDP_CATEGORIES`, and resolves the export format per file at read time.

## Guidance

- Keep the locale table in the platform module: `locale -> key -> list of extension-less paths`, keyed as `source.role` (e.g. `youtube.watch_history`). Adding a locale must stay a single self-contained block; nothing outside the platform module — the shared `Language` enum included — may need editing to add one.
- Entries are path *suffixes* matched by `ZipArchiveReader.resolve_member`, so give each one at least one folder segment whenever the filename occurs in more than one folder of the archive (every `My Activity` product exports the same filename). Only as many trailing segments as are needed to be unambiguous.
- Each entry may list several variants, tried in order, most specific first. Variants carry unverified locales and format eras; a filename-only variant is a legitimate last resort, but never for a filename that is not unique in the archive.
- Record the formats a source can be exported in per key and probe them at read time, returning which one was found so the caller knows how to parse it. Takeout asks for the format per source, so one archive can hold the watch history as JSON and the Chrome history as HTML; a single `ddp_filetype` for the DDP is meaningless.
- Validate in the platform's own `validate_file()` (ADR-0013 permits this; WhatsApp does the same), returning a small platform-local validation object carrying the status code, the locale and `archive_members`. Do not define `DDP_CATEGORIES` you do not match against — a category with empty `known_files` divides by zero in `infer_ddp_category`.
- Score locales on the folder-qualified variants first, using the number of sources found only to break ties: the filename-only variants exist to be forgiving about folders and would otherwise drown out the folder evidence. Treat an archive as valid as soon as one known source is found — participants choose which sources to export.
- Do not extend shared validation to match paths. It is used by every platform, and the multi-source problem is the platform's.

## Why

Google Takeout translates folder *and* file names, one archive holds many sources whose filenames collide across folders, and the export format is chosen per source. The shared validator answers none of that: it compares bare filenames — `validate_zip` drops the directories before `infer_ddp_category` sees them — so it can neither disambiguate two `MyActivity.json` files nor recognise a locale that translates only its folders, and its `DDPCategory` pairs the archive with one file format that a Takeout archive does not have. Paths answer all three, and `resolve_member` already matches them on a path boundary from the right. Costs: the platform carries validation logic other platforms get for free, and a wrong path costs exactly one silently empty table, so unverified locales need a per-locale extraction test built from the table.

## Checks

- Confirm the platform's locale table has the same key set for every locale, and that every key an extractor references exists in it.
- Confirm a DDP built from each locale's paths extracts every table, for each format its sources support.
