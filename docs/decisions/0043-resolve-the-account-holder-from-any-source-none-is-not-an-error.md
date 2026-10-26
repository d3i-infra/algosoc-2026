---
status: accepted
date: "2026-10-23"
category: Extraction
applies_to:
    - packages/python/port/helpers/account_holder.py
    - packages/python/port/platforms/facebook.py
    - packages/python/port/platforms/instagram.py
priority: default
companions:
    - packages/python/tests/test_facebook_redaction.py
    - packages/python/tests/test_instagram_redaction.py
    - packages/python/tests/test_account_holder.py
---

# Resolve the account holder from any source; none is not an error

## Decision

Each platform resolves the account holder from the export's own files in a fixed order, the package name last, and redacts the result from every extracted table through the shared `redact_account_holder` pass. Resolving nothing is an expected outcome, not an error, and extraction continues.

## Guidance

- Call each source via `attempt` on the resolver's own `ZipArchiveReader` (fresh `Counter`): a missing, unreadable or misshapen file yields its empty default, never an exception or an extraction error.
- Keep the order fixed in each platform's `_resolve_account_holder`: the export's own files first, the package name (the zip, or the wrapper folder of a renamed zip) last, and a later source fills only what is still missing, never replacing what an earlier one found. Add a source to the order rather than replacing one, since any export category may be missing.
- Return an `AccountHolder` (names through `cleaned`, longest first; the identifier is the username, or on Facebook the account id when there is no username) and redact after `run_extraction` with `redact_account_holder`: names matched whole across any whitespace, the identifier as a token, addresses as `[email]`. A platform supplies its column lists, its `identifier_expression` and any option the pass offers; review rejects a platform's own copy of the redaction loop.
- Log counts and booleans, never a value: the extraction tail logs `names=<n> identifier=<bool>` at INFO, and `attempt`'s warning names only the source and the exception type. No name, username, id or package name enters a log line.
- When nothing resolves, no error is raised or counted; the INFO line records the outcome. The pass still runs, so addresses are still redacted, and extraction continues. Review rejects a raise, an error count or a participant-facing stop for an unresolved account holder.

## Why

A participant can deselect any export category, so no single file may be the only source of the names to redact, and an export that names nothing does not block extraction.
