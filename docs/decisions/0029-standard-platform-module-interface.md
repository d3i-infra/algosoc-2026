---
status: accepted
date: "2026-05-20"
tags:
    - platform-dispatch
    - platform-interface
    - script
    - config
category: Python architecture
applies_to:
    - packages/python/port/platforms/**/*.py
    - packages/python/port/script.py
priority: default
checks:
    - desc: platform configs are committed in this study — .gitignore must not ignore them
      grep: '^\*_config\.json'
      in: [".gitignore"]
      expect: absent
---

# Standard platform module interface

## Decision

`script.py` stays platform-agnostic: it validates the platform's config, imports `port.platforms.<platform>`, and dispatches through `module.process(session_id)` alone — never naming a platform. Around that seam, each platform module follows a common authoring convention — `EXTRACTOR_REGISTRY`, `extraction(...)`, a `<Platform>Flow(FlowBuilder)` subclass, and `process(session_id)` — with documented signature exceptions.

## Guidance

- `script.py`'s only dispatch dependency is `module.process(session_id)`: it calls `validate_or_raise(platform)`, imports `port.platforms.<platform>`, and calls `process()`. No platform names, no `PLATFORM_REGISTRY`.
- Platform-authoring convention (used inside the module, not by the dispatcher): each exposes `EXTRACTOR_REGISTRY` (ordered `dict[str, Callable[..., pd.DataFrame]]`), `extraction(...)`, a `<Platform>Flow(FlowBuilder)` subclass, and `process(session_id)` returning `<Platform>Flow(session_id).start_flow()`. `example.py` is the canonical template.
- A runnable/released platform needs a generated `configs/<platform>_config.json`, validated at runtime by `script.py` (the config lifecycle and overwrite policy are their own record). This study commits its platform configs — `facebook`, `instagram`, `tiktok`, `google` — alongside the example and test-only configs upstream tracks, and `.gitignore` must not ignore `*_config.json`. A change reaches the committed file either by rm-and-regenerate from the docstrings or by curating within the surface the config-lifecycle record allows; either way the result is committed. The deployed selector regenerates a platform's config from the docstrings (`generate-config --stdout`) rather than reading the committed file, so anything the study needs *there* — the table set above all — is expressed in `EXTRACTOR_REGISTRY` and the `Table config::` blocks, not only in the JSON. Adding a platform still requires no change to `script.py`.
- Documented signature exceptions, both still exposing all four convention symbols: **Netflix** keeps `run_extraction` but with a different `extraction(reader, selected_user)` shape; **WhatsApp** has an `extraction(df)` shape and still calls `load_port_config`, but *bypasses* `run_extraction`, building its tables in its own loop.

## Why

`script.py`'s only dependency on a platform is `module.process(session_id)`, so adding a platform never touches it and no `PLATFORM_REGISTRY` list has to be maintained (that list was a real burden on master). The authoring convention around the seam (`EXTRACTOR_REGISTRY`, `extraction`, `<Platform>Flow`) is deliberately conventional rather than enforced: Netflix (`extraction(reader, selected_user)`) and WhatsApp (pre-parsed DataFrame, own table loop) genuinely need different shapes. The committed configs are this study's design artifact and its build input outside the selector: the preview workflow builds every platform from the checkout's config files, `pnpm start`/`check-deps.sh` need the file on disk, and the curated JSON (the ten Google tables, the study's titles) belongs in version control rather than on one researcher's disk. The deployed selector is the one consumer that does not read them — it regenerates from the docstrings — which is why the study's table set is enforced in the registry too. Costs: the `"<platform>"` string is duplicated across filename, module path, and `load_port_config` with nothing cross-checking them; conformance rests on review and the `example.py` template, not a gate; and a committed config can drift from its docstrings until it is regenerated.

## Checks

- Confirm each *platform* module under `port/platforms/` (excluding `__init__.py` and any non-platform support files) exposes `EXTRACTOR_REGISTRY`, `extraction`, a `<Platform>Flow(FlowBuilder)` subclass, and `process`; allowlist Netflix/WhatsApp for signature divergence only.
- Confirm `script.py` dispatches only via `validate_or_raise` + `import_module("port.platforms.<platform>")` + `process()`, with no per-platform names or `PLATFORM_REGISTRY`.
- The frontmatter check keeps `.gitignore` from re-ignoring `*_config.json`; confirm the four study configs stay tracked (`git ls-files packages/python/port/configs/`).
