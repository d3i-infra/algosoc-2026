---
status: accepted
date: "2026-03-13"
tags:
    - validation
    - ddp-categories
    - fail-fast
category: Extraction
applies_to:
    - packages/python/port/helpers/flow_builder.py
    - packages/python/port/helpers/validate.py
    - packages/python/port/platforms/**/*.py
    - packages/python/port/helpers/meta_recognition.py
    - packages/python/port/platforms/instagram.py
priority: default
companions:
    - packages/python/tests/test_validate.py
    - packages/python/tests/test_flow_builder.py
    - packages/python/tests/test_meta_recognition.py
    - packages/python/tests/test_instagram_recognition.py
---

# Validate DDP categories before extraction

## Decision

`FlowBuilder.start_flow()` runs each platform's `validate_file()` before `extract_data()`, so extraction receives a `ValidateInput` and may assume valid input.

## Guidance

- Do not call `extract_data()` before validation or bypass `FlowBuilder.start_flow()` to reach extraction directly.
- A platform that validates through `validate_zip` (the default) checks the archive against its `DDP_CATEGORIES`; keep its `DDP_CATEGORIES` aligned with the files `extract_data()` actually reads.
- Invalid validation returns the retry prompt; it is not an extraction error or traceback path.
- A Meta platform recognises its export through `meta_recognition.validate_meta`, which scores the zip's folder names against the platform's folder markers as an any-of: accept only when at least one of our product's markers is present and none of the other product's are. Any marker of the other product present means the export is never accepted (`<other>_detected` or `mixed`), however many of ours there are. Such a platform's `DDP_CATEGORIES` only name the format (json/html) and no longer drive recognition. Instagram does this now; Facebook still validates through `validate_zip` until its mirror lands.
- Instagram rejects a recognised export that holds none of the study's categories (`no_study_categories`, applied by `InstagramFlow.validate_file`), so the participant stays pending and sees the retry prompt instead of completing through the no-data page.
- Re-derive the marker lists in `meta_recognition.py` from real export listings whenever Meta's export layout changes; they are not documentation of the layout.
- The invariant is validate-before-extract, not `DDP_CATEGORIES` specifically. WhatsApp (own `validate_file()`, single-file export), Google (`validate_ddp` over the `ArchiveSet` inventory) and Instagram (`validate_meta`) are the standing exceptions to the `DDP_CATEGORIES` contract and still validate before extraction.

## Why

Uploaded zips are routinely the wrong platform, wrong format, or corrupt, and extraction is expensive and fails cryptically on bad input — a raw `KeyError` after all the parsing is useless to a participant. Validating first fails fast with a meaningful retry prompt and lets `extract_data()` assume a recognised archive; centralizing the order in `start_flow()` means no platform can reach extraction first. The ordering, not `DDP_CATEGORIES` itself, is the invariant: WhatsApp's chat export is a single file, and Google's Takeout has no stable filename set, so neither fits a `DDP_CATEGORIES` list. Instagram and Facebook exports share a layout and file names, so a `known_files` share cannot tell them apart or survive Meta renaming files; folder markers can, and one shared helper will keep both platforms judging the same way. Cost: a platform's recognition logic (`DDP_CATEGORIES`, folder markers, or its own validator) must stay aligned with real exports, or invalid files slip through or valid ones are refused.

## Checks

- Aside from the e2etest platforms (excluded from release builds, ADR-0004) and the non-normative `example.py` template, confirm `platforms/google.py` and `platforms/whatsapp.py` are the only modules under `port/platforms/` that define no `DDP_CATEGORIES`, and that each instead exposes its own validator (`validate_ddp` / `validate_file`).
- Confirm `google.validate_ddp` takes an `ArchiveSet` and never calls `zipfile.ZipFile(...)` itself — recognition runs over `archive_set.members`, not a fresh unzip.
- Confirm `instagram.validate_ddp` delegates to `validate_meta` and does not read `known_files` for recognition.
- Confirm the rejection paths are pinned by tests: `mixed` and `<other>_detected` in `packages/python/tests/test_meta_recognition.py`, `no_study_categories` in `packages/python/tests/test_instagram_recognition.py`.
