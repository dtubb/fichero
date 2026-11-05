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
10. **Trailers.** One `Written-By: <model>` line on every commit, naming who wrote the code (owner 2026-11-05); a commit from before that ruling, or one already queued, may carry the old `Directed-By: the maintainer` line instead, and no `Co-Authored-By:` is required. Author `Claude <noreply@anthropic.com>`, whatever model wrote it (the authorship checks accept no other).
11. **Ladder output is untrusted.** Tests run the worker's own code, so a green ladder is never evidence against a hostile
    diff (a test file can always exit 0). Read every new module for exits and for names that shadow the stdlib or an
    installed package, and every conftest.py change. Name each such file on the last line: `READY: allow-shadow <path>`.
