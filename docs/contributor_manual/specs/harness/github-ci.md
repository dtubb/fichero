# GitHub CI and security tools — Design Spec

> Milestone: harness
> Manual: contributor-facing.

> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent

The repository is public, so GitHub Actions (including macOS arm64 runners), CodeQL, secret scanning and Dependabot cost
nothing. They add a second, independent reading of every change beside the builder's own ladder; they do not replace
it. Spec-change: owner 2026-11-20.

## Dependabot

- `ci.dependabot` [GAP] — `.github/dependabot.yml` opens weekly update PRs (version and security) against `integration`
  for `fichero-server` (uv, reading `uv.lock`), the Swift packages under `fichero/` and `fichero/fichero-api-client`,
  and GitHub Actions. Minor and patch updates are grouped per ecosystem and labelled `dependencies` plus the ecosystem.
  Dependabot edits the manifests and `Package.resolved` itself; nobody edits a `Package.resolved` by hand.
  `fichero-builder` has no manifest or lock file today, so it has no entry; adding a `pyproject.toml` or requirements
  file there is what would bring it in. Acceptance: `.github/dependabot.yml` parses, is `version: 2`, and every entry has
  `target-branch: integration`, a weekly schedule and a `directory` that exists in the tree.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_dependabot_yml_targets_integration_weekly_over_directories_that_exist` in fichero-server/tests/unit/scripts/.
