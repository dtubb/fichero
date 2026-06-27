---
description: Manager selector for the next Fichero work batch — deterministic ROADMAP.md + GitHub issue picker.
name: choose-next
---

# /choose-next

Pick the next worker-sized batch without claiming anything.

## Steps

1. Run the selector from the repository root:
   ```bash
   scripts/choose_next.py
   ```

2. Use the output as the handoff target for `/session-start-worker` or the
   worker dispatcher:
   - one `one-big` issue for a keystone/cross-cutting worker, or
   - one `small-batch` of 3-10 issues from the same milestone.

3. Claim each selected issue only when a worker starts it:
   ```bash
   gh issue edit <N> --add-assignee @me --add-label "status:in-progress"
   ```

## Notes

- The selector reads `docs/ROADMAP.md` for tier order and milestone mapping.
- It reads GitHub milestones/issues with `gh`.
- It skips assigned issues and issues labelled `status:in-progress`.
- It is read-only; it never edits GitHub state.
- For automation, use:
  ```bash
  scripts/choose_next.py --json
  ```
