---
status: accepted
date: "2026-03-13"
tags:
    - prompt-components
    - feldspar-compatibility
    - ux
category: Data collector
applies_to:
    - packages/data-collector/src/components/**
    - packages/python/port/helpers/port_helpers.py
companions:
    - packages/python/tests/test_port_helpers_prompts.py
    - packages/data-collector/src/file_drop/copy.test.ts
priority: default
---

# Prefer standard feldspar prompts; drag-and-drop for file uploads

## Decision

In this repo, prefer a standard feldspar prompt and add a D3I custom prompt only when no standard one can provide the required UX. File uploads are that case: ask for files with the D3I drag-and-drop file inputs (`PropsUIPromptFileInputSingle`, `PropsUIPromptFileInputMultiple`), never with feldspar's `PropsUIPromptFileInput`.

## Guidance

- Ask for a file with `port_helpers.generate_file_prompt`, never feldspar's `props.PropsUIPromptFileInput`; for any other prompt, reach for a standard feldspar prompt first.
- Call `generate_file_prompt(extensions)` for one file and `generate_file_prompt(extensions, multiple=True)` for several; render the returned prompt with `ph.render_page(...)` like any other prompt.
- Do not announce drag-and-drop to participants: no participant-facing copy — the prompt `description`, the multi prompt's `example` placeholder, or the components' built-in text — mentions dragging or dropping. The copy tells participants to choose a file.
- Put the file inputs' browser behaviour (choosing a file in the picker, dropping files onto the prompt) in `packages/data-collector/src/components/file_input_single/`, `packages/data-collector/src/components/file_input_multiple/` and the shared modules in `packages/data-collector/src/file_drop/`; never edit feldspar's `packages/feldspar/src/framework/visualization/react/ui/prompts/file_input.tsx` to get it, because feldspar is not modified for D3I features.
- Add a new D3I custom prompt only when the UX genuinely can't be met by a standard one (e.g. a consent form with data visualizations). It needs a factory registered in data-collector and carries maintenance and bug risk (e.g. the single-button `PropsUIPromptRetry` defect, exposed once FlowBuilder actually checked the retry response).

## Why

Standard prompts inherit upstream fixes and host compatibility for free; every custom prompt is a standing maintenance liability that pays for itself only when the UX demands it, as drag-and-drop file selection does for uploads.
