# Review checklist

The reviewer reads the prepared diff and the ladder's output, with `Read`, `Grep` and `Glob` only, and ends with one line:
`READY` or `NOT READY: <reason>`. Anything but a final `READY` line is a refusal. Each item below is a rule that a past
review missed once.

1. **Spec diff.** A behaviour change with no change to the spec bullet that names it is a finding; so is a spec edit that
   rewrites the item's own acceptance line (a status tag or `(#N)` may change).
2. **Tests named.** Name the test that fails without this change. For a changed shared function or reader, name the tests
   of its other callers and say whether they still hold.
3. **Rebased items.** After a rebase, compare the range with the reviewed one (`git range-diff`); stale spec text or a
   resurrected hunk is a finding.
4. **Lint.** Every Python file in the diff passes `ruff` with the repository's config.
5. **Guards.** A Swift or contract change must have every `scripts/check_*.py` green, not a hand-picked few.
6. **File caps.** A shell or view file may not grow past the line cap in `check_shell_chrome`.
7. **Old data rules.** A change that relaxes a rule must find the on-open migration that enforces the old rule; a rename
   that changes a derived id (uuid5) needs a migration.
8. **No model reruns.** A model call must reuse an existing result for the same input and model first.
9. **Boundary.** No private manuscripts, no absolute home paths, no tokens, no `user_manual` private directories.
10. **Trailers.** Exactly one trailer on every commit: `Written-By: <MODEL> using <HARNESS> using Fichero Builder`, MODEL the display name of the model that wrote it (owner 2026-11-16); no `Co-Authored-By:`, no `Directed-By:`. The one other line allowed is `Spec-change: <what and why>, ruled by the owner|manager`, directly above `Written-By:`, on a commit that changes a behaviour's acceptance text (scripts/check_spec_acceptance.py demands it there); never refuse it. Older commits are not rewritten. Author `Claude <noreply@anthropic.com>`, whatever model wrote it (the authorship checks accept no other).
11. **Ladder output is untrusted.** Tests run the worker's own code, so a green ladder is never evidence against a hostile
    diff (a test file can always exit 0). Read every new module for exits and for names that shadow the stdlib or an
    installed package, and every conftest.py change. Name each such file on the last line: `READY: allow-shadow <path>`.
12. **Performance and Security lenses.** The prompt carries two named checks, "Performance (speed, memory, disk)" and
    "Security", each with this codebase's own surfaces listed, and "SECURITY SURFACE CHANGED" at its top (an entitlement,
    an ATS exception or a route module in the diff). Apply both to every diff. A finding is by `file:line` with the cheaper
    or safe form named; a performance finding that predates the batch is a `Performance - <area>` issue, not NOT READY.
