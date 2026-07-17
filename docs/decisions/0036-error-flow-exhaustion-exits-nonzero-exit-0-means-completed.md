---
status: accepted
date: "2026-07-17"
tags:
    - termination
    - host-integration
    - error-handling
source: 'Issue #123'
category: Feldspar
applies_to:
    - packages/python/port/main.py
priority: invariant
companions:
    - packages/python/tests/test_main_queue.py
    - tests/error-flow.spec.ts
checks:
    - desc: the error-handler exhaustion branch emits the nonzero exit
      grep: 'CommandSystemExit\(1, "Error flow completed"\)'
      in: ["packages/python/port/main.py"]
      expect: present
    - desc: the error flow ends on the task-incomplete page, not a stale error page
      grep: 'render_task_incomplete_page'
      in: ["packages/python/port/main.py"]
      expect: present
---

# Error-flow exhaustion exits nonzero; exit 0 means completed

## Decision

The exit code is the completion signal across the bridge: only genuine flow-end exits 0. When the consent-gated error flow exhausts, `ScriptWrapper.send()` returns `CommandSystemExit(1, "Error flow completed")`, so the host keeps the task incomplete (retry navigation remains host behavior).

## Guidance

- Never let the error path exit 0 — hosts treat exit 0 as task completion with no donation check (mono's `crew_task_helpers.ex` calls `handle_tool_exited()`), so an error-end exit 0 records an errored participant as completed.
- Keep the exit `info` a fixed PII-free literal; traceback and exception text leave the iframe only via the consent-gated `error-report` donation.
- `error_flow()` terminates by yielding `ph.render_task_incomplete_page()` — a single-button Confirm that resolves so the generator can exhaust; a display-only page holding an unresolved promise would suppress the exit signal entirely.
- This refines, not contradicts, the no-in-iframe-end-page rule: success still renders no terminal page (the host owns completion UI); the task-incomplete page is a *resolvable pre-exit acknowledgment* compensating for the host's minimal nonzero-exit UI, and must never become a permanent unresolved end page.
- Changing exit-code semantics is a workflow↔host contract change: coordinate hosts and ship it with a version bump and migration notes.

## Why

Mono completes the crew task on exit 0 without checking that anything was donated, so an error path exiting 0 silently converts errored participants into satisfied completions — invisible in funnel analysis, and completion/payment signals can fire with zero data (Issue #123).
