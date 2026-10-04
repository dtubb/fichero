# Milestone template (spec-led)

> `_`-prefixed: the spec guardrails ignore this file.

**Name:** the spec's file name without `.md` (e.g. `preview-surface`). `check_spec_milestones.py`
enforces that spec name = milestone name = test tag. GitHub matches milestone names
CASE-INSENSITIVELY, so never create one differing only in case from another. Move issues by milestone
NUMBER (`gh api -X PATCH repos/dtubb/fichero/issues/<n> -F milestone=<number>`).

**Description** (first line is what GitHub shows):

    Spec: docs/contributor_manual/specs/<area>/<name>.md
    Goal: <one sentence: what a person can do when this milestone is done>
    Done when: every behaviour in the spec is [OK] or explicitly deferred with an issue;
    UX and server both done; no open issue without a spec behaviour.

**Hygiene:**
- Each open issue cites a behaviour in the spec, or is the task of writing one.
- Close issues as they are fixed (`Fixes #N` plus `scripts/close_fixed_issues.py --apply`).
- `needs-your-test` and `needs-your-decision` surface through `scripts/maintainer_queue.py`.
- Legacy capitalised milestones (pre-spec buckets) are folded into spec milestones as their issues are
  touched; the ops buckets (Bugs, Lint, Ratchets, Performance, Testing Overhaul) stay as they are.
