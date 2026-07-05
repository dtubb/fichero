# fichero-engine subdir audit (#2552)

Scope audited: `fichero-engine/bin/`, `fichero-engine/scripts/`, `fichero-engine/evals/`, `fichero-engine/DEPS-UPDATE.md`.

Method: checked tracked files only (`git ls-files`), then traced current references from repo docs/tests/code with `rg`. This report describes what is built and referenced now, not intended future use.

## Live and supported

- `bin/fm-bridge/`
  - Live. `src/fichero/llm.py` points at both `bin/fm-bridge/build.sh` and `bin/fm-bridge/FmBridge.swift`, and `tests/unit/test_release_scripts.py` asserts the release pipeline packages the built binary.
  - Conclusion: supported build input for the Apple Intelligence bridge, not dead.

- `scripts/start_backend.sh`
  - Live. Referenced from root `AGENTS.md`, `docs/CLAUDE.md`, `CONTRIBUTING.md`, `fichero/README.md`, app services, and contributor docs.
  - Conclusion: canonical local backend launcher.

- `scripts/sync_openapi_schema.sh`
  - Live. Referenced from root `AGENTS.md`, `docs/CLAUDE.md`, contributor docs, engine/app READMEs, and release memory/history notes.
  - Conclusion: canonical contract sync entry point.

- `scripts/export_openapi_schema.py`
  - Live. Called by `scripts/sync_openapi_schema.sh` and checked by root `scripts/verify_python.sh`.
  - Conclusion: internal-but-supported helper.

- `scripts/generate_openapi_cli.py`
  - Live. Called by `scripts/sync_openapi_schema.sh`; generated CLI file points back to it.
  - Conclusion: internal-but-supported generator.

- `scripts/seed_test_library.py`
  - Live. Used by `fichero-engine/tests/integration/_seedlib.py` and Swift engine-harness tests in `fichero/fichero-tests/EngineHarness.swift`.
  - Conclusion: shared test fixture builder, actively used cross-stack.

- `scripts/validate_model_sync.py`
  - Live. Called by root `scripts/verify_all.sh` and referenced by `scripts/verify_report.py` and contributor docs.
  - Conclusion: active guardrail helper.

- `scripts/build_backend_bundle.sh`
  - Live. Referenced by `pyproject.toml`, engine `README.md`, release tests, and multiple bundled-backend docs.
  - Conclusion: current Briefcase bundle build entry point.

- `scripts/xcode_copy_backend.sh`
  - Live. Referenced by bundled-backend docs and release tests.
  - Conclusion: active Xcode packaging helper.

- `scripts/clean_local_artifacts.sh`
  - Live but narrow. Referenced by engine `README.md`.
  - Conclusion: supported cleanup helper.

- `scripts/start_backend.py`
  - Live. Copied by `scripts/bundle_python_backend.sh`; covered by `tests/unit/test_start_backend_scheme_warning.py`.
  - Conclusion: real bundled-backend entry point, even if it is not a common manual entry point.

- `evals/`
  - Live, manual-use tooling. `src/fichero/prompts.py` documents `python -m evals.run`; `tests/unit/test_evals_runner.py` imports and tests it; `evals/README.md` describes the shipped scenarios/criteria layout.
  - Conclusion: not integrated into the normal gate, but current and supported as a prompt-eval harness.

## Likely stale or orphaned

- `scripts/batch_verify.py`
  - I found no references outside the file itself.
  - Conclusion: likely orphaned. Safe candidate for manager verification and possible removal/issue.

- `scripts/bundle_python_backend.sh`
  - Not called by `scripts/build_backend_bundle.sh`. Current references are only `scripts/README.md` and `tests/unit/test_release_scripts.py`.
  - The script builds a standalone Python resource bundle under `fichero/fichero/Resources/python`, which is a different packaging path from the current Briefcase nested-app flow described in `pyproject.toml` and `build_backend_bundle.sh`.
  - Conclusion: likely stale alternate packaging path. Needs manager verification before removal because tests/docs still mention it.

- `scripts/run_migration.py`
  - Current references are only `scripts/README.md` and `docs/architecture/api/key_files.md`.
  - No tests or runtime callers point at it.
  - Conclusion: maybe still useful as a manual migration CLI, but currently docs-only. Candidate for verification as stale-or-supported-manual.

- `scripts/validate_repo.sh`
  - Current references are only `scripts/README.md`, `docs/architecture/api/key_files.md`, and `agent-work/VALIDATION.md`.
  - It runs heavyweight local `xcodebuild` and full guardrails directly, while current root `AGENTS.md` assigns the real gate to manager/integrator flows instead.
  - Conclusion: likely stale as a canonical workflow script; at minimum its “CI / pre-commit” description looks outdated.

## Orphaned or misplaced docs

- `DEPS-UPDATE.md`
  - No inbound references found.
  - Content is a dated dependency/bundle-size audit note (`Last updated: 2026-06-27`), not a runtime entry point or subtree contract.
  - Conclusion: likely misplaced durable doc. Better home would be `docs/release/` or `docs/architecture/` if it should stay, otherwise it is an orphaned audit note.

## README drift inside `scripts/`

- `scripts/README.md` covers only the small “official” subset and omits real live helpers such as:
  - `generate_openapi_cli.py`
  - `seed_test_library.py`
  - `batch_verify.py`
- It still presents `bundle_python_backend.sh`, `run_migration.py`, and `validate_repo.sh` as supported without clarifying that they currently look docs-only or alternate-path.
- Conclusion: the README is incomplete and partially stale relative to the actual tree.

## Non-findings

- Untracked `__pycache__/` files under `evals/` and `scripts/` showed up in a raw filesystem scan but are not tracked by git, so they are not part of this audit.

