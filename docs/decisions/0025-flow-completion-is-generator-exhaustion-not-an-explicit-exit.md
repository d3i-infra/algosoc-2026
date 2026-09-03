---
status: accepted
date: "2026-04-14"
tags:
    - termination
    - completion
    - host-integration
category: Feldspar
applies_to:
    - packages/python/port/main.py
    - packages/python/port/script.py
    - packages/python/port/helpers/flow_builder.py
    - packages/feldspar/src/framework/command_router.ts
    - packages/data-collector/src/components/notice/notice.tsx
priority: invariant
companions:
    - packages/python/tests/test_flow_builder.py
checks:
    - desc: no EndPage factory remains
      grep: 'EndPageFactory'
      in: ["packages/feldspar/src/**", "packages/data-collector/src/**"]
      expect: absent
    - desc: no end-page prop remains
      grep: 'PropsUIPageEnd'
      in: ["packages/python/port/**", "packages/feldspar/src/**"]
      expect: absent
    - desc: no render_end_page helper remains
      grep: 'render_end_page'
      in: ["packages/python/port/**"]
      expect: absent
    - desc: no explicit CommandSystemExit in the flow (only ScriptWrapper emits it)
      grep: 'CommandSystemExit'
      in: ["packages/python/port/script.py", "packages/python/port/helpers/flow_builder.py"]
      expect: absent
    - desc: no explicit ph.exit() yielded by the flow
      grep: 'ph\.exit\('
      in: ["packages/python/port/script.py", "packages/python/port/helpers/flow_builder.py"]
      expect: absent
---

# Flow completion is generator exhaustion, not an explicit exit

## Decision

Study completion is signaled by generator exhaustion, not an explicit exit: `script.py`'s last yield is a log milestone, the generator returns, and `ScriptWrapper.send()` converts the `StopIteration` into `CommandSystemExit(0, "End of script")`, which the bridge forwards so the host renders its own completion UI (mono's `finished_view`). There is no in-iframe end page.

## Guidance

- Don't yield an explicit exit from `script.py` or `FlowBuilder.start_flow()` — they `return`; only `ScriptWrapper` emits `CommandSystemExit`, so termination has one path.
- Don't add an in-iframe end / "thank you" page: it duplicates the host's completion UI, and a display-only page that holds an unresolved render promise silently blocks the final yield from returning (the EndPage hang).
- `FlowBuilder.start_flow()` returns after one platform — it never ends the study; `script.py` owns the lifecycle and its final act is `emit_log("Study complete")`.
- A display-only page must resolve its render promise itself; `PropsUIPromptNotice` is the one sanctioned shape, used only on incomplete endings where the blocked exit would be nonzero.

## Why

The host marks the task complete and shows its checkmark only on `CommandSystemExit`; anything that blocks the final yield from returning strands the participant — and looks fine in local testing. It happened for real: a "Thank you" EndPage whose render promise nothing resolved hung Python at the last yield, so `StopIteration` never fired and the host never got its exit. A general auto-resolving discipline was rejected as something every future display-only page would have to remember; the study still has no completion end page (deleted, matching upstream). `PropsUIPromptNotice` is the one narrow, sanctioned exception — a single reusable component the incomplete-ending handlers yield, not a discipline each new page author must reinvent — so the exit still fires with no participant action. One termination path — ScriptWrapper's conversion — means no ambiguity about who owns the exit.
