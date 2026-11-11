# HANDOFF: lane-ie, #6473 (Documents table chevron level with the icon)

## State at the head (84802edc1; the harness has rewritten hashes before, so find commits by message)
- Done and committed: `LibraryTableDisclosureAlignment.swift` (pure `chevronY`, plus the `LibraryTableDisclosureAligner` AppKit probe), one `.background(...)` line in `LibraryView+TableView.swift`, and `LibraryTableDisclosureAlignmentTests`.
- The probe moves the system disclosure buttons (identifier `NSOutlineView.disclosureButtonIdentifier`) to `min(centred, 3pt)`. It drops its observers when the view leaves its window (a `deinit` cannot touch them under Swift 6).
- Spec bullets: `sidebar.table-chevron-level-with-first-line` in `sidebar-crud.md`; `dev-workflows.console.abandoned-after-six-hours` in `harness/dev-workflows.md`, in Step 4.9.
- Also fixed on this branch: fake interpreter shebangs in `fichero-builder/tests` (a path with a space, the gate disk, broke them), `test_verify_whole_lists.py` for a repo-less gate copy, the panes nav entry, the `m2p.window-minimum-ignores-measured-width` acceptance text (now a `Built:` note), a neutral path in `test_loop.py`.

## Not verified
- No Swift was compiled by me; the builder's compile is the first real check. The `deinit` fix at least is expected to clear the last build error.
- The 3 pt icon inset is an estimate: look at a tall row in the running app. If the probe does nothing, AppKit may not expose the buttons as row-view subviews.
- I never ran pytest, ruff or swiftlint (none installed here); I ran some fixtures by hand.

## Open, not mine, left alone
- `0bc3b945d` and `952d7f52f` lack `Written-By:`. They are already on `origin/integration`, so only a published-history rewrite fixes them. The manager must decide: reword upstream, or measure the range from `origin/integration` (all 14 branch commits there have the trailer).
- `test_every_control_gating_callback_is_supplied_by_every_host` finds 20 omitted callbacks, on the base too.
- "Not red on base" for `test_guard_inputs.py`: the change predates this lane.

## Next step
Wait for the builder's compile and the reviewer; fix only what they report. End with `DONE <sha>`; do not run `done`.
