---
status: accepted
date: "2026-09-29"
category: Data collector
applies_to:
    - packages/data-collector/src/file_drop/accept.ts
    - packages/data-collector/src/components/file_input_single/file_input_single.tsx
    - packages/data-collector/src/components/file_input_multiple/file_input_multiple.tsx
priority: default
companions:
    - packages/data-collector/src/file_drop/accept.test.ts
checks:
    - desc: the single-file prompt passes incoming files through partitionAccepted
      grep: 'partitionAccepted\('
      in: ["packages/data-collector/src/components/file_input_single/file_input_single.tsx"]
      expect: present
    - desc: the multi-file prompt passes incoming files through partitionAccepted
      grep: 'partitionAccepted\('
      in: ["packages/data-collector/src/components/file_input_multiple/file_input_multiple.tsx"]
      expect: present
---

# Refuse a file in the prompt only on a clear type mismatch

## Decision

Refuse a file only when its name ends in an extension (a non-leading dot, then 1 to 10 ASCII letters or digits) and the accept string disallows both that extension and its MIME type, ignoring case, including each type's known aliases and extensions. Accept every other file, name every refused file to the participant, and leave upload rejection to Python.

## Guidance

- Refuse a file only if it has an extension and the prompt's accept string allows neither that extension nor its MIME type; accept every file the check in `accept.ts` cannot judge.
- Accept a file with no extension, and treat an accept string that is empty or holds a token `parseAccept` cannot interpret as open to every file.
- Compare extensions and MIME types without regard to case.
- Treat a name whose last dot is its first character, such as `.hidden`, and a name that ends in a dot, such as `archive.`, as having no extension.
- Treat a name whose part after the last dot is not 1 to 10 ASCII letters or digits, such as `facebook-john.doe-2026-01-01`, as having no extension.
- When you add a MIME type to `KNOWN`, list all its aliases and extensions, since a zip can arrive as `application/x-zip-compressed` or with an empty type.
- Pass every incoming file through `partitionAccepted`, for files chosen in the picker as well as dropped files; a participant can switch the operating system's dialog to show all files.
- Show a notice naming each refused file, built with `rejectedNotice` and `buildNotices` from `packages/data-collector/src/file_drop/copy.ts`; never drop a file silently.
- Never let this check replace or relax a check in Python: do not remove or loosen the upload size guard (`uploads.check_payload_size`) or zip and DDP validation (`validate_file`) in `FlowBuilder.start_flow()` because the prompt already checks file types.
- When a file of the wrong type gets past the prompt, let Python's validation send the participant to the retry prompt; do not tighten this check to catch it.

## Why

A check that refuses a valid export blocks the donation outright, while a file of the wrong type that gets through only costs the participant the retry prompt.
