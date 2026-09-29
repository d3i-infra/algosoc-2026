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
priority: default
forbids:
    - packages/data-collector/src/components/file_input/**
companions:
    - packages/python/tests/test_port_helpers_prompts.py
    - packages/data-collector/src/file_drop/copy.test.ts
checks:
    - desc: no data-collector code claims feldspar's PropsUIPromptFileInput type
      grep: '[''"]PropsUIPromptFileInput[''"]|isPropsUIPromptFileInput\b'
      in: ["packages/data-collector/src/**"]
      expect: absent
    - desc: feldspar does not export its FileInput component
      grep: '\bFileInput\b'
      in: ["packages/feldspar/src/index.ts"]
      expect: absent
    - desc: the single-file prompt renders the loading notice
      grep: '<LoadingNotice'
      in: ["packages/data-collector/src/components/file_input_single/file_input_single.tsx"]
      expect: present
    - desc: the multi-file prompt renders the loading notice
      grep: '<LoadingNotice'
      in: ["packages/data-collector/src/components/file_input_multiple/file_input_multiple.tsx"]
      expect: present
---

# Prefer standard feldspar prompts; drag-and-drop for file uploads

## Decision

In this repo, prefer a standard feldspar prompt and add a D3I custom prompt only when no standard one can provide the required UX. File uploads are that case: ask for files with the D3I drag-and-drop file inputs (`PropsUIPromptFileInputSingle`, `PropsUIPromptFileInputMultiple`), never with feldspar's `PropsUIPromptFileInput`, whether from Python or from data-collector.

## Guidance

- Never use feldspar's `PropsUIPromptFileInput` or `FileInput`: no data-collector factory claims that type, and `FileInput` is not wrapped or exported from feldspar's `index.ts`.
- Ask for a file through the D3I file prompts: `port_helpers.generate_file_prompt` in Python, rendered by the components in `file_input_single/` and `file_input_multiple/`; change those two rather than adding another file prompt.
- Call `generate_file_prompt(extensions)` for one file and `generate_file_prompt(extensions, multiple=True)` for several; render the returned prompt with `ph.render_page(...)` like any other prompt.
- Render anything shown while an upload is processed, such as `LoadingNotice`, inside both `file_input_single.tsx` and `file_input_multiple.tsx`, in the row of the Continue button; never in only one of them or in a component around them.
- Do not announce drag-and-drop to participants: no participant-facing copy — the prompt `description`, the multi prompt's `example` placeholder, or the components' built-in text — mentions dragging or dropping. The copy tells participants to choose a file.
- Put the file inputs' browser behaviour (choosing a file in the picker, dropping files onto the prompt) in `packages/data-collector/src/components/file_input_single/`, `packages/data-collector/src/components/file_input_multiple/` and the shared modules in `packages/data-collector/src/file_drop/`; never edit feldspar's `packages/feldspar/src/framework/visualization/react/ui/prompts/file_input.tsx` to get it, because feldspar is not modified for D3I features.
- For any other prompt, reach for a standard feldspar prompt first. Add a new D3I custom prompt only when the UX genuinely can't be met by a standard one (e.g. a consent form with data visualizations). It needs a factory registered in data-collector and carries maintenance and bug risk (e.g. the single-button `PropsUIPromptRetry` defect, exposed once FlowBuilder actually checked the retry response).

## Why

Standard prompts inherit upstream fixes and host compatibility for free; every custom prompt is a standing maintenance liability that pays for itself only when the UX demands it, as drag-and-drop file selection does for uploads. Once that one exception exists, a second file prompt anywhere else is pure cost: Python never sends feldspar's type, so it is either dead or it drifts from the one participants see.
