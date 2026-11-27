# Code Organisation — how the tree is laid out and kept tidy — Design Spec

> Milestone: code-organization
> Manual: docs/contributor_manual/swiftui-development-standards.md — the "File Organization & Size Guidelines" section
> carries the Swift half for contributors; `backend-development-standards.md` gets a matching "Where a module lives"
> section when Step 1.1 lands. No user-manual section: this is a contributor rule set.

> **Status: APPROVED by the owner 2026-11-14 (the six rulings in the last section folded into the bullets they decide;
> owner request 2026-11-14: a spec for how the code is organised and kept tidy, and a review of the tree against it; the
> review is `agent-work/reviews/code-organization-review-2026-11-14.md`, the first-wave briefs `agent-work/briefs/code-org/`).**
> Tags: **[OK]** built and enforced · **[PARTIAL]** a guard exists, the rule is wider than it checks · **[GAP]** a rule with no
> guard. Issues: #1944 (folders), #1945 (dead files), #1941 (Xcode registration), #4446 (lint ratchet), #1915 (comment
> hygiene), #3040 (shell size), #2569 (routes grouping), #2566 (engine package reorg), #6318 (`--since` guards).
>
> Scope with other docs: `AGENTS.md` "Where Things Live" stays the short rule for agent scratch and the repo root; this spec
> is the long form for product code and the one the guards cite. `design/swiftui-app-reorg.md` (2026-07) and
> `agent-work/design/engine-package-reorg.md` (2026-07) are the surveys this spec grew from; their **shim strategy is
> superseded** by `AGENTS.md` rule 0 (a move is a hard cutover in one commit, never an alias module).

## Intent

A contributor or an agent who knows one feature finds its code in one place, names tell what a file holds before it is
opened, nothing in the tree is unreachable, no file is too big to review, and every one of these holds by a guard that
runs on the builder, not by a sweep: the files a batch adds or moves are judged in that batch, the tree's old debt nightly. Two trees: the SwiftUI app under `fichero/fichero` with its tests under
`fichero/Tests`, and the Python engine under `fichero-server/src/fichero_server` with its tests under
`fichero-server/tests` (the CLI, MCP and Builder packages follow the same rules). Measurements in this spec are from
2026-11-14 at `7438dd2f5d`.

## Prior art (reuse, do not invent)

- **Feature folders**, not layer folders, for SwiftUI: Apple's sample apps and the SwiftUI community put a feature's
  views, its view-local state and its previews together; shared layers stay small. The app already does this under
  `Views/<Feature>/`; `Models/` and `Services/` are the two layer folders that outgrew the pattern.
- **One type per file, `Type+Topic.swift` for extensions**: the Swift API design guidelines and SwiftLint's
  `file_types_order`/`file_name` rules; the app's `ContentView+*.swift` family is the local example.
- **Python src layout and PEP 8 module names**: `src/<package>/<domain>/<module>.py`, `snake_case`, a module named for
  what it does; tests mirror the package tree (pytest's convention and the engine's own `tests/unit/<package>/`).
- **Dead code by tool, not by eye**: `periphery` for Swift (whole-project, needs an index build, so nightly),
  `vulture` for Python (static, seconds, so per batch), jcodemunch `find_dead_code` for the import graph, and the repo's
  own `check_dead_files.py`. The existing guard's blind spot (a file reached only through an extension) is why the
  adopted tools are the rule and the home-made scanner is the floor.
- **Ratchets, held exactly**: `check_swiftlint_warning_ratchet.py` (#4446), `check_coverage_ratchet.py` (#4249),
  `check_release_size_ratchet.py` (#4444): a committed baseline, a count that may never rise, `--update-baseline` as a
  decision. The compiler-warnings ratchet below copies that shape.

## What exists today (measured 2026-11-14)

| Concern | Guard | Runs | Notes |
|---|---|---|---|
| Catch-all Swift folders | `scripts/check_folder_organization.py` | per batch | >18 loose files in one folder, or a named mixed-concern folder; 8 known offenders |
| Dead Swift files | `scripts/check_dead_files.py` | per batch | primary type referenced nowhere else; 18 known candidates, 5 of them false positives (extension-only files) |
| Swift file in the target | `scripts/check_xcode_registration.py` | per batch | synchronized root, so a file on disk compiles; catches `membershipExceptions` |
| Shell file size | `scripts/check_shell_chrome.py` rule 3 | per batch | `ContentView*` / `Sidebar*` ≤ 1000 lines, no allowlist |
| SwiftLint sizes | `.swiftlint.yml`, `fichero/.swiftlint.yml` | per batch (errors) | file 400 warn / 1000 error; type 250 / 500; function 50 / 100; line 140 / 200 |
| SwiftLint warnings | `scripts/check_swiftlint_warning_ratchet.py` | `--since` per batch; whole tree nightly | baseline 123 in `scripts/swiftlint_warning_baseline.json`; harness.toml `since_guards` |
| Per-file lint ratchet | `fichero-builder/fichero_builder/lint.py` | ready check, per batch | swiftlint and ruff by rule per touched file against the base; a new file must be clean |
| Python lint | `ruff.toml` (`E4 E7 E9 F`) | per batch | error-only set, zero tolerance; no warning class to ratchet |
| Commented-out code | `scripts/check_comment_hygiene.py`, `scripts/check_python_comment_hygiene.py` | per batch | 3+ code-like comment lines; `TODO` must cite an issue |
| Duplicate handlers | `scripts/check_duplicate_paths.py` | per batch | same METHOD+PATH twice, two KG row writers |
| Compiler warnings (Swift) | none | — | the build rung keeps `error:` lines only (`check_tool.py`) |
| Type checking (Python) | none | — | no pyright or mypy anywhere in the repo |
| Dead Python | none | — | no vulture; jcodemunch `find_dead_code` is advisory |

## Behaviours

### A. Folders

- `code-org.folders.root` [OK] — The repo root holds governance docs (`AGENTS.md`, `CLAUDE.md`, `CONSTITUTION.md`,
  `CONTRIBUTING.md`, `README.md`, `USER.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `LICENSE`, `LICENSING.md`, `NOTICE`,
  `CLA.md`, `CODE_OF_CONDUCT.md`), repo-wide config (`mkdocs.yml`, `features.yaml`, `harness.toml`, `ruff.toml`,
  `.swiftlint.yml`, `coverage-baseline.json`, `requirements-docs.txt`, `.python-version`) and the product and tooling
  directories (`fichero/`, `fichero-server/`, `fichero-cli/`, `fichero-mcp/`, `fichero-builder/`, `scripts/`, `docs/`,
  `agents/`, `agent-work/`, `test-fixtures/`, `icons/`, `web/`, `pipeline/` until its removal). Nothing else: a new file
  at the root is misplaced. Not built: `AGENTS.md` lists the rule, no guard reads the root (#1944; issue to file under
  this milestone). Test (to write): guard `check_repo_root` with the allowlist above and a `--self-test`.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py (`check_file_placement` whole-tree mode, baselined in KNOWN_VIOLATIONS; `--since` judges each new file).
- `code-org.folders.swift-layers` [OK] — The app has five top-level folders under `fichero/fichero`: `App/` (lifecycle,
  windows, menus, `AppState`), `Models/` (stores and domain types), `Services/` (engine clients and manual services),
  `Intents/` (App Intents and AppleScript entry points), `Views/` (the UI), plus `Resources/`. A sixth is a ruling.
  Test: fichero-server/tests/unit/scripts/test_check_folder_organization.py (the scan floor names the tree).
- `code-org.folders.swift-feature-folders` [PARTIAL] — Under `Views/` a feature's files live in `Views/<Feature>/`, with
  subfolders when a feature passes 18 loose files (`Views/Library/ViewModes/Canvas/2D/` is the shape). A folder holds one
  feature; a folder named for a layer (`Views/Models/`) or for a single file is wrong. Built: the 18-file limit and two
  named mixed-concern folders (#1944). Not built: a single-file folder check and the layer-name check. Test:
  `scripts/check_folder_organization.py`.
- `code-org.folders.swift-models-services-by-feature` [GAP] — `Models/` and `Services/` carry one subfolder per feature
  (`Models/Segments/`, `Services/Pairing/`), named as the matching `Views/<Feature>/`; the flat root of each holds only
  cross-feature types. Today 355 and 220 files sit flat; both are known offenders of the 18-file rule since #1944 and the
  guard's allowlist lets them grow. Test: `scripts/check_folder_organization.py` once the two entries leave its
  `KNOWN_VIOLATIONS`.
  Was: the allowlist let them grow; now each `KNOWN_VIOLATIONS` entry carries its file count at baseline (355 and 220) and the
  guard fails when a count rises.
- `code-org.folders.swift-view-local-state` [OK] — A view's own `@Observable` state (a `*State`, `*Model` or `Focused*`
  type used by one feature) sits BESIDE its views in `Views/<Feature>/`; `Models/<Feature>/` holds shared state, read by
  two or more features (ruled by the owner 2026-11-14). Today 38 observable types sit under `Views/`; the guard names the
  ones a second feature reads (#1944). Built: `check_folder_organization` reports an `@Observable`/`ObservableObject` type
  under `Views/<Feature>/` that another `Views/<Other>/` or `App/` reads, with "→ Models/<Feature>/ (read by two features)";
  today's 18 are baselined (`KNOWN_SHARED_STATE`), new ones fail, `--list` names them.
  Test: fichero-server/tests/unit/scripts/test_check_folder_organization.py; `check_folder_organization --self-test`.
- `code-org.folders.swift-test-mirror` [OK] — `fichero/Tests/Unit/<platform>/<Layer>/<Feature>/` mirrors
  `fichero/fichero/<Layer>/<Feature>/`, `Tests/UI/<platform>/<Feature>/` the surfaces; a test of `Views/Segments/` goes
  under `Tests/Unit/general/Views/Segments/`. Shared helpers (`TestFixtures.swift`, `AppSource.swift`, `EngineHarness.swift`)
  sit at `Tests/Unit/general/` root. Built: the tree has the shape; 437 model tests sit flat because `Models/` is flat.
  Built: `check_folder_organization` reports a test folder
  `Tests/Unit/<platform>/<Layer>/<Feature>/` with no app folder to mirror (today 2, baselined in `KNOWN_TEST_ORPHANS`).
  Test: fichero-server/tests/unit/scripts/test_check_folder_organization.py; `check_folder_organization --self-test`.
- `code-org.folders.python-packages` [OK] — Engine code lives in one domain package under
  `fichero-server/src/fichero_server/`: `api/` (routes by resource under `api/routes/<resource>/`, transport, startup),
  `models/`, `db/`, `core/` (small utilities with no domain), `llm/`, `media/`, `formats/`, `importers/`, `knowledge/`,
  `workflows/` (+ `tools/`), `recipes/`, `execution/`, `training/`, `security/`, `transfer/`, `remote_read/`, `finddocs/`,
  `checking/`, `actions/`, `mcp/`. The package root holds `__init__.py`, `__main__.py` and nothing else. Built: the
  packages exist (#2566, #2569). Not built: 18 modules still sit loose at the root (`export_service.py`, `histdate.py`,
  `sync_folder.py`…) and nothing refuses a new one. Test (to write): guard `check_engine_package_layout`, root allowlist
  of two files.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py (`check_file_placement` whole-tree mode, baselined in KNOWN_VIOLATIONS; `--since` judges each new file).
- `code-org.folders.python-no-shim-modules` [OK] — A moved module leaves nothing behind: no `from new import *` plus a
  `sys.modules[__name__]` alias (`AGENTS.md` rule 0). Today 18 such modules sit under `api/routes/` (`kg_*.py`,
  `folders.py`, `search_explain.py`, all "Moved to … (#2569)"), `api/main.py` imports 17 of them and 31 other files the
  rest. Test (to write): `check_engine_package_layout` refuses a module whose body assigns `sys.modules[__name__]`.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py (`check_file_placement` whole-tree mode, baselined in KNOWN_VIOLATIONS; `--since` judges each new file).
- `code-org.folders.python-test-mirror` [OK] — `fichero-server/tests/unit/<package>/` mirrors a package of
  `fichero_server`; `tests/unit/scripts/` tests `scripts/`; `tests/unit/cli/` and `tests/unit/mcp/` test the sibling
  products until their own `tests/` dirs join the gate; `tests/integration/`, `tests/contracts/`, `tests/perf/` are the
  other legs. Built: 44 of 55 unit dirs match a package. Not built: `jobs/` (119 files, tests `execution/`), `kg/` (27,
  tests `knowledge/` and `api/routes/kg/`), `transport/` (29, tests `security/` and `api/`), `export/` (12, tests a
  module with no package), `check/`, `harness/`, `seams/`, `activity/`, `packaging/` match nothing (#2566). Test (to
  write): `check_engine_package_layout` compares the two dir sets.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py (`check_file_placement` whole-tree mode, baselined in KNOWN_VIOLATIONS; `--since` judges each new file).
- `code-org.folders.scripts-vs-package` [OK] — `scripts/` holds repo-wide gates and tooling (`check_*.py`, `verify_*.sh`,
  release and site scripts); code the engine runs lives in the package, code the builder runs in
  `fichero-builder/fichero_builder/`; a guard imports only the stdlib and its two helpers (`_scan_files.py`,
  `_check_floor.py`). Test: `fichero-builder/tests/test_no_engine_import.py`.

### B. Naming

- `code-org.naming.swift-file-is-type` [OK] — A Swift file is named for the one primary type it declares;
  `Type+Topic.swift` holds an extension of `Type` and declares no second public type; `#Preview` and `private` helper
  types may share the file. A file holding a family of wire types for one service is named `<Service>Types.swift` and is
  the one allowed bundle (ruled by the owner 2026-11-14: kept). Today 135 files match none of their types and 303 declare more than two top-level types. Built:
  SwiftLint `file_length`/`type_body_length` bound the size, not the count. Built (#1944): `check_swift_one_type_per_file`, baselined per
  file in `KNOWN_VIOLATIONS`, the count may only fall; it also judges the View shape word and place and the `IOS`/`MacOS`
  spelling (`code-org.naming.swift-views-end-view`, `code-org.naming.swift-platform-suffix`).
  Test: fichero-server/tests/unit/scripts/test_check_swift_one_type_per_file.py; `check_swift_one_type_per_file --self-test`.
- `code-org.naming.swift-views-end-view` [OK] — A `View`-conforming type ends in `View`, or in one of the shape words
  the shell uses (`Pane`, `Sheet`, `Row`, `Bar`, `Button`, `Menu`, `Picker`, `Popover`, `Cell`, `Badge`, `Label`,
  `Overlay`, `Section`, `Item`, `Field`, `Panel`, `Strip`, `Card`, `Line`, `Notice`, `Pill`); a type under `Views/` that
  is not a view is named for what it is (`*Policy`, `*State`, `*Model`). A View type outside `Views/` lives in
  `App/Menus/` (menu commands) or is misplaced. Today 33 View types sit outside `Views/`, 30 of them menus (#1944).
  Built: `check_swift_one_type_per_file` rule 3, baselined; `check_file_placement` judges a new one by the same rule. The
  guard's `SHAPE_WORDS` also accepts the shapes the tree already uses (`Host`, `Content`, `Modifier`, `Stage`, `Screen`, `Page`,
  `Tab`, `Tabs`, `Toolbar`, `Header`, `Footer`, `Chip`, `Indicator`, `Banner`, `Grid`, `List`, `Stack`, `Canvas`, `Editor`,
  `Viewer`, `Inspector`, `Reader`, `Sidebar`, `Window`, `Scene`, `Renderer`, `Commands`), and a `*Scene` or `*Window` under
  `App/` (the app's own window roots) may stay outside `Views/`.
  Test: fichero-server/tests/unit/scripts/test_check_swift_one_type_per_file.py; `check_swift_one_type_per_file --self-test`.
- `code-org.naming.swift-platform-suffix` [OK] — A platform-specific file or type ends in `IOS` or `MacOS` (ruled by the owner
  2026-11-14); today 13 files use `IOS`, 2 use `iOS`, 1 uses `MacOS`, so the two `iOS` files are renamed. Built: `check_swift_one_type_per_file` rule 4 flags a file or type ending `iOS`,
  `macOS` or `iOSOnly`, baselined (#1944).
  Test: fichero-server/tests/unit/scripts/test_check_swift_one_type_per_file.py; `check_swift_one_type_per_file --self-test`.
- `code-org.naming.python-modules` [OK] — A Python module is `snake_case` and named for what it does
  (`segment_readings.py`, `kraken_runtime.py`), never for its layer alone (`utils.py`, `helpers.py`) and never a stdlib
  name at the package root (`core/logging.py` is inside a package and allowed). Every module in the four products passes.
  Test: fichero-server/tests/unit/scripts/test_check_python_comment_hygiene.py (the scan floor walks every module); the
  name rule rides with `check_engine_package_layout` when it lands.
- `code-org.naming.python-tests` [OK] — A test file is `test_<what_it_proves>.py`, in the folder mirroring the code
  it tests; when it pins an issue the number is a suffix, `test_<what>_<issue>.py` (553 of 2,434 files, the convention in
  use). A prefix form (`test_6085_one_listing.py`, one file) is wrong. A behaviour id from a spec goes in the docstring,
  not the name. Built: `test_globs` in `harness.toml`. Not built: the suffix rule (#1915). Test (to write): one rule in
  `check_engine_package_layout`.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py (`check_file_placement` whole-tree mode, baselined in KNOWN_VIOLATIONS; `--since` judges each new file).
- `code-org.naming.swift-tests` [OK] — A Swift test file ends in `Tests.swift` and names the type or surface it covers
  (`PageImageGridTests.swift`); the 11 non-test helpers (`TestFixtures`, `AppSource`, `EngineHarness`…) carry no suffix.
  Test: `scripts/check_swift_test_self_references.py`.

### C. Dead code

- `code-org.dead.no-unused-files-swift` [PARTIAL] — No Swift file whose types nobody else references. Built:
  `check_dead_files.py` (#1945) with 18 known candidates. Not built: `periphery` as the whole-project tool, nightly, so
  the extension-only false positives (5 of 18) stop living in an allowlist. Test: `scripts/check_dead_files.py`; (to
  write) `check_periphery_ratchet`, nightly, baseline count never rising.
- `code-org.dead.no-unused-python` [GAP] — No Python module, function or class with zero references, and no route that
  no client, CLI command or MCP tool reaches. `vulture` at confidence 80 over the four packages, baselined and shrink-only,
  per batch (seconds); jcodemunch `find_dead_code` stays the advisory cross-check. Today one module has no reference
  anywhere (`media/image_prep_samples.py`) (#1945; issue to file). Test (to write): guard `check_vulture_ratchet` with
  `--self-test` planting an unused function.
- `code-org.dead.test-only-code` [PARTIAL] — Production code reached only by its own test is dead with a pension: delete the
  code and the test together. The 6 Swift types reached only from `fichero/Tests` (`CacheModel`, `DragDropModel`,
  `MCPServersSheet`, `IntegrationsPlaceholderSheet`, `PageImageGrid`, `FicheroShortcuts`) go with their tests (ruled by the
  owner 2026-11-14; review batch S5). Test (to
  write): `check_dead_files` counts a reference from `fichero/Tests` separately and reports "test-only" (#1945).
  Built: S5 deleted `CacheModel`, `MCPServersSheet` and `IntegrationsPlaceholderSheet` with their tests; `DragDropModel` and
  `PageImageGrid` wait for a later batch (diff bound); `FicheroShortcuts` stays, as the Shortcuts and Siri phrases are a
  product feature. `ScrollWheelZoom`, `SimpleWorkflowView`, `WorkflowExecutionView` and `WorkflowChainListView` (with its
  parts) are outside ruling 3 and stay, with their `KNOWN_VIOLATIONS` waivers, until the owner rules on them. Guard: `scripts/check_dead_files.py`; test: `fichero-server/tests/unit/scripts/test_check_dead_files.py`.
- `code-org.dead.no-commented-out-code` [OK] — No commented-out code blocks; a `TODO`/`FIXME` cites an issue. Test:
  fichero-server/tests/unit/scripts/test_check_comment_hygiene.py, fichero-server/tests/unit/scripts/test_check_python_comment_hygiene.py.
- `code-org.dead.waiver` [PARTIAL] — A deliberate keep is a `KNOWN_VIOLATIONS` entry (or a `# noqa: vulture` /
  `// periphery:ignore` comment) that names the issue and the reason in one line; an entry whose file is gone fails the
  guard; the list only shrinks. Built: the pattern in `check_dead_files.py` and `check_duplicate_paths.py`. Not built: no
  guard refuses an entry with no `#NNNN` (#1945). Test (to write): `_check_floor.require_reasoned_allowlist` shared by
  the guards.

### D. Size

- `code-org.size.swift-file` [OK] — A Swift file is under 400 lines (warning) and never over 1000 (SwiftLint error, the
  gate); shell files (`ContentView*`, `Sidebar*`) never over 1000 with no allowlist (#3040). A type body is under 250
  lines (warning), 500 (error); a function under 50, 100. Today one file is over 1000 (`SpaceSceneView.swift`, 1169,
  under an inline `swiftlint:disable file_length`) and 86 are between 400 and 1000. Test: fichero-builder/tests/test_lint.py (the per-file size ratchet),
  `scripts/check_shell_chrome.py` rule 3.
- `code-org.size.swift-split` [OK] — A split is by concern into `Type+Topic.swift` extensions or into sub-views in their
  own files, in the same folder; never `Helpers.swift`. A new file under `fichero/fichero` compiles by being on disk
  (synchronized root, `AGENTS.md` rule 10); a move is `git mv`; `scripts/add-swift-file.rb` and
  `scripts/remove-swift-file.rb` are for the test targets and for a `membershipExceptions` entry, never a hand edit of
  `project.pbxproj`. Test: fichero-server/tests/unit/scripts/test_check_xcode_registration.py.
- `code-org.size.python-file` [GAP] — A Python module is under 1,500 lines (ruled by the owner 2026-11-14: 1,500, as a
  ratchet); a generated module (`*_generated.py`) is exempt; the gate is a ratchet (no module grows past its own count, the count of modules over the line never rises).
  Today 84 non-generated modules are over 1,000 and 8 over 3,000 (`db/__init__.py` 8,503; `workflows/tools/vision_base.py`
  6,430; `api/routes/document/segments.py` 6,150; `execution/jobs.py` 5,554; `llm/__init__.py` 5,119). A package
  `__init__.py` re-exports and holds no logic beyond 200 lines. Test (to write): `check_python_file_size_ratchet`, baseline
  json beside the swiftlint one (#2566).
- `code-org.size.python-split` [GAP] — A split moves whole functions and classes into a sibling module named for the
  concern (`segments.py` → `segments/` package with `readings.py`, `conversion.py`…), every importer repointed in the same
  commit, no re-export left behind unless the package `__init__` is the public door. Test: the ready check's
  `red_on_base` and `scripts/check_openapi_route_set_current.py` prove nothing moved off the contract (#2566).

### E. Ratchets and when they run

- `code-org.enforce.per-batch-placement` [OK] — Every batch is checked for where it put its files, not only the nightly
  tree: a guard beside `check_folder_organization.py`, `check_file_placement --since <base>`, reads `git diff --name-status
  <base>..HEAD` and judges each ADDED or RENAMED path (the new name) against the rules of this spec: a Swift file under
  `fichero/fichero/<Layer>/<Feature>/` whose layer and feature exist and whose name follows `code-org.naming.swift-*`, with
  its test under the mirror folder of `fichero/Tests` when the batch adds a test; a Python module inside a package of
  `fichero_server` (never the package root), `snake_case`, its test under `tests/unit/<package>/` named
  `test_<what>[_<issue>].py`; nothing new at the repo root or at `api/routes/` root; no new module that aliases
  `sys.modules`. A misplaced file is red with the path it should have, one line per file (the file, an arrow, the folder it belongs in, and the rule in
  a few words). Wired through `harness.toml` `since_guards` on `fichero/` and `fichero-server/`
  (the `--since` shape of #6318), so it runs in the guards rung of every batch under the 60 s budget; the whole-tree
  question stays with `check_folder_organization.py`. A deleted or modified-in-place file is not judged (the tree's debt is
  the nightly guard's). Built (#1944): the guard `check_file_placement` with a `--self-test`
  that stages a synthetic range holding one right and one wrong file per rule; a pytest under
  `fichero-server/tests/unit/scripts/` that runs it over a temp repo.
  Built (#6607): the Python and repo-root rules, wired on every diff (`since_guards` prefix ""); a new test also passes in a
  `tests/unit/` folder the merge-base already had. The Swift rules are built too: a new `.swift` under `fichero/fichero/` sits
  in a layer folder, a new View type under `Views/<Feature>/` or `App/Menus/`, the name passes the file-is-type, shape-word and
  `IOS`/`MacOS` rules, and a new test under `fichero/Tests/Unit/` is `*Tests.swift` in the mirror of an existing app folder.
  Test: fichero-server/tests/unit/scripts/test_check_file_placement.py; `check_file_placement --self-test`.
- `code-org.ratchet.per-batch` [OK] — Every `scripts/check_*.py` not in `harness.toml` `guard_skip` runs on each batch in
  the builder's guards rung, under 60 s each, from the pinned copy; the ready check runs `lint.py` per touched file;
  `since_guards` runs `check_swiftlint_warning_ratchet.py --since <base>` when the diff touches `fichero/`. Test:
  `fichero-builder/tests/test_build_check.py`.
- `code-org.ratchet.nightly` [OK] — The whole-tree and build-needing guards run in the nightly gate (`guard_skip`, reasons in
  `pipeline/projects/fichero.toml` `[ladder.skip]`): `check_swiftlint_warning_ratchet` over the whole app,
  `check_coverage_ratchet`, `check_release_size_ratchet`, `check_hang_ratchet`, `check_test_plans_runnable`. Test:
  fichero-builder/tests/test_verify_all.py.
- `code-org.ratchet.swift-compiler-warnings` [GAP] — The build rung's `xcodebuild` log from a CLEAN build (incremental
  builds report only the files they recompiled) is counted for `warning:` lines, deduplicated by file, line and text, in
  two buckets: hand-written (`fichero/fichero`, `fichero/Tests`, the client package's own `Sources/`) and generated (the
  swift-openapi-generator plugin output under `BuildToolPluginIntermediates`, `*.generated.swift`), each against a committed
  baseline (`swift_compiler_warning_baseline.json` beside the swiftlint one in `scripts/`, ruled by the owner 2026-11-14)
  that never rises; a lower count
  prints the number to lower it to, `--update-baseline` is a decision in its own commit. Per batch because the build already
  runs; nightly on the Release configuration too. Checked 2026-11-14: nothing counts warnings today (`check_tool.py`
  `build` keeps `error:` lines) (#4446; issue to file). Test (to write): guard `check_swift_compiler_warning_ratchet
  --log <path>` with a `--self-test` over a synthetic log holding both buckets, wired as a build-rung post-step.
- `code-org.ratchet.generated-warnings-fixed-at-source` [GAP] — A warning in generated code is never fixed by editing the
  generated file (`AGENTS.md` rule 3). It is fixed where it comes from, in this order: the generator config
  (`fichero/fichero-api-client/Sources/FicheroAPIClient/openapi-generator-config.yaml`), the generator or runtime package
  version (`Package.swift` range and `Package.resolved` pin), the target's Swift settings (upcoming features, import
  access levels), the OpenAPI schema the engine emits. Last resort: a baseline entry in the generated bucket naming the
  upstream issue and the reason, dropped when upstream ships. Worked example (owner's build, 2026-11-14): 3× "public
  import of 'Foundation' was not used in public declarations" and 1× the same for `OpenAPIRuntime` in the generated
  `Types.swift`. Cause: swift-openapi-generator 1.13.0 (its PR #883) puts `public import` of `OpenAPIRuntime` and of
  `Foundation.URL/.Data/.Date` at the head of every generated file, and since 1.13 the output is split into nine files, so
  `Types.swift` (the `APIProtocol` only) uses none of them in a public declaration; upstream issue #968, a duplicate of
  #946, fix pending in PR #947 (Swift 6.4 warning suppression). Not fixable from the config (`accessModifier: public` is
  what the app needs), not from a target setting (SE-0443 has no per-group suppression), not from the schema (the schemas
  file uses `Date` 412 times; the warning is per file). The fix that applies is the **package version**: the repo pins
  1.10.3 (`Package.resolved`), which is warning-free, but `Package.swift` says `from: "1.6.0"`, so the owner's Xcode
  resolved 1.13.1 and built the warnings the builder never sees. Cap the range at `"1.6.0"..<"1.13.0"` until #947 ships,
  so every machine resolves the same generator (#4446; issue to file). Test (to write): `check_swift_compiler_warning_ratchet`
  refuses a generated-bucket baseline entry with no upstream reference; a `Package.swift` range test in
  `fichero/fichero-api-client/Tests/`.
- `code-org.ratchet.python-type-warnings` [GAP] — `pyright` in basic mode over the four packages, errors and warnings
  counted against a committed baseline (`pyright_baseline.json` in `scripts/`), never rising; nightly first (minutes over 373 modules), per batch with
  `--since` on touched files once the whole-tree count is stable. ruff needs no ratchet: its set is error-only and at
  zero. Checked 2026-11-14: no pyright or mypy in the repo (#4446; issue to file). Test (to write): guard
  `check_pyright_ratchet` with `--self-test`.

### F. Enforcement map

| Rule | Guard today | Status |
|---|---|---|
| placement of every added or renamed file, per batch | `check_file_placement --since` (Python and root) | [PARTIAL] the Swift rules are not built |
| root allowlist | — | [GAP] `check_repo_root` |
| Swift feature folders, 18-file cap | `check_folder_organization.py` | [OK] with 8 known offenders |
| Models/Services by feature | `check_folder_organization.py` allowlist | [GAP] until the two entries leave |
| Swift test mirror | — | [GAP] in `check_folder_organization` |
| Python package root, test mirror, shims, test names | — | [GAP] `check_engine_package_layout` |
| one type per file, View suffix, platform suffix | `check_swift_one_type_per_file.py` (`fichero-server/tests/unit/scripts/test_check_swift_one_type_per_file.py`) | [OK] built; `KNOWN_VIOLATIONS` ratchets the baseline |
| dead Swift files | `check_dead_files.py` | [OK]; periphery nightly [GAP] |
| dead Python | — | [GAP] `check_vulture_ratchet` |
| commented-out code | `check_comment_hygiene.py`, `check_python_comment_hygiene.py` | [OK] |
| Swift sizes | SwiftLint, `check_shell_chrome.py`, `lint.py` | [OK] |
| Python sizes | — | [GAP] `check_python_file_size_ratchet` |
| SwiftLint warnings | `check_swiftlint_warning_ratchet.py` | [OK] per batch `--since`, nightly whole tree |
| Swift compiler warnings, two buckets | — | [GAP] `check_swift_compiler_warning_ratchet` |
| generated warnings fixed at source | — | [GAP] same guard + the generator range cap |
| Python type warnings | — | [GAP] `check_pyright_ratchet` |

## Build order

### Stage 1 — guards first, then the tree

#### Step 1.0 — placement checked on every batch
- Behaviours: `code-org.enforce.per-batch-placement`
- Tests: `check_file_placement --self-test`; fichero-server/tests/unit/scripts/test_check_file_placement.py; harness.toml `since_guards` gains the guard, proved by fichero-builder/tests/test_guard_inputs.py
- Size: M

#### Step 1.1 — the engine layout and root guards
- Behaviours: `code-org.folders.root`
- Tests: (to write) `check_engine_package_layout`, `check_repo_root`, each with `--self-test`; baselined on today's tree
- Depends on: 1.0
- Size: M

#### Step 1.2 — the Swift file guard
- Behaviours: `code-org.naming.swift-file-is-type`, `code-org.folders.swift-view-local-state`, `code-org.folders.swift-test-mirror`
- Tests: `check_swift_one_type_per_file` (built); new rules in scripts/check_folder_organization.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — the ratchets
- Behaviours: `code-org.ratchet.swift-compiler-warnings`, `code-org.ratchet.python-type-warnings`, `code-org.size.python-file`, `code-org.dead.no-unused-python`, `code-org.dead.no-unused-files-swift`
- Tests: (to write) `check_swift_compiler_warning_ratchet`, `check_pyright_ratchet`, `check_python_file_size_ratchet`, `check_vulture_ratchet`, `check_periphery_ratchet`; fichero-builder/tests/test_build_check.py for the build-rung post-step
- Depends on: 1.1
- Size: M

#### Step 1.4 — the generator range cap
- Behaviours: `code-org.ratchet.generated-warnings-fixed-at-source`
- Tests: fichero/fichero-api-client/Tests/FicheroAPIClientTests/GeneratorRangeCapTests.swift; (to write) the generated bucket of `check_swift_compiler_warning_ratchet` at zero on a clean build
- Depends on: 1.3
- Size: S

#### Step 1.5 — dead code out
- Behaviours: `code-org.dead.test-only-code`, `code-org.dead.waiver`
- Tests: scripts/check_dead_files.py (the test-only report), (to write) `_check_floor.require_reasoned_allowlist`
- Depends on: 1.3
- Size: S

### Stage 2 — the tree (one review batch per step; the review names the files)

#### Step 2.1 — shims out of `api/routes`
- Behaviours: `code-org.folders.python-no-shim-modules`
- Tests: scripts/check_openapi_route_set_current.py, fichero-server/tests/unit/api/test_routes_kg_reset_removed.py
- Depends on: 1.1
- Size: S

#### Step 2.2 — loose engine modules into packages
- Behaviours: `code-org.folders.python-packages`
- Tests: (to write) `check_engine_package_layout` with an empty root allowlist beyond the two files
- Depends on: 2.1
- Size: M

#### Step 2.3 — Python test folders renamed to their packages
- Behaviours: `code-org.folders.python-test-mirror`, `code-org.naming.python-tests`
- Tests: (to write) `check_engine_package_layout` mirror rule at zero
- Depends on: 2.2
- Size: M

#### Step 2.4 — `Models/` and `Services/` by feature
- Behaviours: `code-org.folders.swift-models-services-by-feature`
- Tests: scripts/check_folder_organization.py with `Models` and `Services` out of `KNOWN_VIOLATIONS`
- Depends on: 1.2
- Size: M (review lanes S1–S4, one feature cluster each)

#### Step 2.5 — `Views/Components` and `Views/Library` emptied of feature files
- Behaviours: `code-org.folders.swift-feature-folders`
- Tests: scripts/check_folder_organization.py with `Views/Components`, `Views/Library` out of `KNOWN_VIOLATIONS`
- Depends on: 1.2
- Size: M

#### Step 2.6 — names
- Behaviours: `code-org.naming.swift-views-end-view`, `code-org.naming.swift-platform-suffix`
- Tests: `check_swift_one_type_per_file` (built in 1.2); its baseline lowered to the files not renamed
- Depends on: 1.2
- Size: S

#### Step 2.7 — the oversized engine modules split
- Behaviours: `code-org.size.python-split`
- Tests: scripts/check_openapi_route_set_current.py, (to write) `check_python_file_size_ratchet` baseline lowered per module
- Depends on: 1.3, 2.2
- Size: M (review lanes P4, one module each)

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | — | — |
| Backend (pytest) | y | every guard's `--self-test` and the builder's build-rung post-step | `fichero-server/tests/unit/scripts/`, `fichero-builder/tests/` |
| MCP / CLI / UI legs | n | contributor tooling, no user surface | — |

## Rulings (owner, 2026-11-14)

1. View-only `@Observable` state sits beside its view in `Views/<Feature>/`; `Models/` holds shared state
   (`code-org.folders.swift-view-local-state`).
2. The `<Service>Types.swift` wire bundles stay as the one exception to one type per file (`code-org.naming.swift-file-is-type`).
3. The six test-only types are deleted together with their tests, in batch S5 (`code-org.dead.test-only-code`).
4. Platform suffixes are `IOS` and `MacOS` (`code-org.naming.swift-platform-suffix`).
5. The Python size line is 1,500 lines, as a ratchet (`code-org.size.python-file`).
6. The compiler-warnings baseline lives in `scripts/` beside the swiftlint one (`code-org.ratchet.swift-compiler-warnings`).
