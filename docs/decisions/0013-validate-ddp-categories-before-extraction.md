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
priority: default
companions:
    - packages/python/tests/test_validate.py
    - packages/python/tests/test_flow_builder.py
    - packages/python/tests/test_instagram_recognition.py
    - packages/python/tests/test_facebook_recognition.py
---

# Validate DDP categories before extraction

## Decision

`FlowBuilder.start_flow()` runs each platform's `validate_file()` before `extract_data()`, so extraction receives a `ValidateInput` and may assume valid input.

## Guidance

- Do not call `extract_data()` before validation or bypass `FlowBuilder.start_flow()` to reach extraction directly.
- Invalid validation returns the retry prompt; it is not an extraction error or traceback path.
- A platform that validates through `validate_zip` (the default) checks the archive against its `DDP_CATEGORIES`; keep their `known_files` aligned with the files `extract_data()` actually reads.
- The invariant is validate-before-extract, not `DDP_CATEGORIES` specifically. WhatsApp (own `validate_file()`, single-file export), Google (`validate_ddp` over the `ArchiveSet` inventory), and Instagram and Facebook (`validate_ddp` delegating to `meta_recognition.validate_meta`) are the standing exceptions to the `DDP_CATEGORIES` contract and still validate before extraction.

## Why

Uploaded zips are routinely the wrong platform, wrong format, or corrupt, and extraction is expensive and fails cryptically on bad input — a raw `KeyError` after all the parsing is useless to a participant. Validating first fails fast with a meaningful retry prompt and lets `extract_data()` assume a recognised archive; centralizing the order in `start_flow()` means no platform can reach extraction first. The ordering, not `DDP_CATEGORIES` itself, is the invariant: WhatsApp's chat export is a single file, Google's Takeout has no stable filename set, and Instagram and Facebook share a layout and file names that a `known_files` share cannot tell apart. Cost: each platform's recognition logic must stay aligned with real exports, or invalid files slip through or valid ones are refused.

## Checks

- Aside from the e2etest platforms (which `release.sh` excludes from release builds) and the non-normative `example.py` template, confirm `platforms/google.py` and `platforms/whatsapp.py` are the only modules under `port/platforms/` that define no `DDP_CATEGORIES`, and that each instead exposes its own validator (`validate_ddp` / `validate_file`).
- Confirm `google.validate_ddp` takes an `ArchiveSet` and never calls `zipfile.ZipFile(...)` itself — recognition runs over `archive_set.members`, not a fresh unzip.
- Confirm `instagram.validate_ddp` and `facebook.validate_ddp` delegate to `meta_recognition.validate_meta`.
