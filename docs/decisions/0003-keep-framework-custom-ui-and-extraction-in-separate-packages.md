---
status: accepted
date: "2026-03-13"
tags:
    - monorepo
    - package-boundaries
category: Fork governance
applies_to:
    - pnpm-workspace.yaml
    - packages/feldspar/package.json
    - packages/data-collector/package.json
    - packages/python/pyproject.toml
    - packages/mobile-tiktok/package.json
priority: default
---

# Keep framework, custom UI, and extraction in separate packages

## Decision

The repo is a pnpm-workspace monorepo whose packages are kept separate by role and change rate: the upstream-tracked framework, the study UI, the Python extraction runtime, and the standalone mobile app. A package exists per role, never merged into one and never split further within a role.

## Guidance

- Place new code by package role: framework → `feldspar` (rarely; see the alignment rule), custom UI → `data-collector`, extraction/validation → `packages/python` (the `port` distribution), the phone-only TikTok app → `packages/mobile-tiktok`.
- Wire JS package dependencies through the pnpm workspace; deliver the Python package as the Poetry `port` wheel copied into `data-collector/public`. Don't collapse the boundaries to take a shortcut.
- `packages/mobile-tiktok` is a separate runtime, not a consumer of the other three: it imports nothing from them at runtime and reads only `packages/python/port/configs/tiktok_config.json` at build time, so its own record (the mobile-tiktok flow-rules record) governs its internals.

## Why

The packages have different audiences and change rates — an upstream-tracked framework, study UI, extraction logic, and a phone app with an older browser target — and the split mirrors upstream so framework syncs stay clean. Merging them would entangle upstream-tracked code with study code (breaking the alignment rule), and splitting further within a role adds coordination cost for no boundary that isn't already expressible by role. The mobile app earned a package because it targets Safari 12, which the React and Pyodide stack cannot reach, and sharing a build with `data-collector` would mix two browser targets in one package.
