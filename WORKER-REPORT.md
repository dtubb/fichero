# WORKER-REPORT — lane/review (opus governance pass)

**Date:** 2026-06-27 · **Branch:** `lane/review` · **Worktree:** `~/code/fichero-worktrees/ms-review`
**Author of commits:** Claude (`noreply@anthropic.com`), Co-Authored-By: Daniel Tubb · **NOT pushed.**

## What this lane was asked to do

REVIEW + PLAN the repo's governance / structure / agent-harness / docs layer for going public,
**safely harvest** actionable `agent-work/` items as GitHub issues, and — added mid-session by
Daniel — **execute** the `site/docs/` → `docs/` consolidation (the one structural change I own).
Four follow-on instructions arrived during the pass (AGENTS.md canonical framing, architecture-folder
rename, docs-folder consolidation, LICENSE assessment, skills audit) — all folded into the plan.

## Deliverables

- **`PLAN-GOVERNANCE.md`** — the full plan: decision table for every root-governance file/folder,
  the canonical doc-set model, `agent-work/` cleanup plan, `rules.json` assessment, the
  `agents/skills/` audit (per-skill KEEP/UPDATE/MERGE/DELETE verdicts), the architecture-folder
  rename plan (with the ~48-reference impact list), the executed docs-consolidation record, the
  LICENSE assessment, and **8 flagged decisions** for Daniel.
- **`WORKER-REPORT.md`** — this file.
- **1 GitHub issue filed** (see below).
- **Executed: docs consolidation** — `mkdocs build --strict` passes (EXIT 0).

## Executed this session (committed, not pushed)

**Docs consolidation — ONE `docs/` folder that mkdocs publishes AND humans+agents read:**

- Merged curated `site/docs/` (index, faq, how-its-built, `user/`, `developer/`, `api-reference/`,
  `assets/`) into `docs/` via history-preserving `git mv`. `site/` directory removed.
- Parked the 3 *differing* published architecture overviews in `agent-work/docs-reconcile/` (with a
  README) for the **archdocs lane** to reconcile into `docs/architecture/`; dropped the 1 identical one.
- Moved agent scratch out of `docs/` → `agent-work/` (qa, reviews, validation, verify, morning-test,
  orphan-triage, agent-workflow, superpowers, archive, design).
- `mkdocs.yml`: `docs_dir: docs`, `edit_uri: edit/main/docs/`, `site_dir: _site_build`.
- Removed stale `docs/README.md` (conflicted with new `docs/index.md`; links were broken).
- Updated `scripts/deploy-site.sh` + `.gitignore` for the new build dir.
- **Gate:** `mkdocs build --strict` → clean (EXIT 0). 71 renames, 2 deletes, 3 config edits.

I deliberately did **not** edit `README.md`, `USER.md`, `CONTRIBUTING.md`, or `fichero-engine/`
docs (their dangling `site/docs/` links) — those are the docs-content lane's; flagged for the
manager to sweep at merge.

**Skills audit — safe/factual fixes only** (judgment calls left flagged):

- `choose-next` — resynced from its canonical `fs_session` source (was 10 lines behind).
- `dispatch-worker` — stale base branch `0.0.2` → `main` (0.0.2 merged to main via #2652). The
  cherry-pick → PR-merge model reconciliation is left **flagged** (judgment).
- `fichero-build`, `fichero-release-prep`, `fichero-release` — added a **STALE banner** pointing at
  the canonical release lane (`docs/release/release-lane.md` / `scripts/release-all.sh`) rather than
  half-fixing unverifiable Briefcase paths. Full rewrite-or-delete left **flagged**.
- **Found two orphaned dead `_shared` files** (`architecture-summary.md`, `team-constitutions.md`) —
  referenced by no live skill, contradict canonical docs (`fichero-swiftui/`, `fichero-api/`,
  `codex/restructure-api-swiftui`, `xcodebuild test`). **DELETE candidates — flagged**, not touched
  (deletes stay your call).

## Issues harvested → filed

| # | Title | Milestone |
|---|---|---|
| **#2710** | [Workflows] Rationalize the transcribe-family presets — ≤4 canonical, shared config convention, per-page invariant | Workflows & Catalogue Hardening |

Lean by design: a full triage of ~110 `agent-work/` files found that the other "actionable" items
are already filed (image-editing #462–469, graph-RAG #1156, regression harness #1287, WebKit #1346,
per-page fan-out #2303/#2395, KG batch via the prior `2026-05-31-agentwork-review.md`) or are
point-in-time snapshots (reality-checks, milestone-audits) → KEEP-HISTORY. `#2710` is the one
verified net-new item (transcribe family; #1794 only covers catalogue).

## Top findings (detail in PLAN-GOVERNANCE.md)

1. **Committed agent scratch in a soon-public repo** — `STATE.md`, `MEMORY.md` (116 KB),
   `HISTORY.md` (205 KB), `HISTORY-worker.md`, `rules.json`, `project.yaml` are tracked & public even
   though `.claude/.codex/.ai` were just privatized. The core "make less AI-specific" tension. **(Flag)**
2. **Skills are vendored copies** — 4 of 5 `fs_session` skills in `agents/skills/` are byte-identical
   to `~/code/fichero-skills`; `choose-next` is 10 lines behind. `dispatch-worker` is **stale**
   (worktrees off `0.0.2`, now `main`; cherry-pick vs Daniel's PR-merge model). The 3 build/release
   skills reference the **old `fichero-api` dir** (renamed `fichero-engine`) + Briefcase paths → STALE.
3. **`rules.json` is a generic agent-guard policy**, not Fichero config — recommend moving it private
   with `.claude/.codex`. **(Flag)**
4. **`docs/agent-workflow/skills/` duplicated `agents/skills/`** — resolved by moving it to
   `agent-work/` this session.
5. **Architecture doc folders are named by tech, not component** — `docs/architecture/swiftui/`
   + `/api/` should become `/fichero/` (recommended) + `/fichero-engine/`. ~48 refs to update.
   Flagged + scoped, **not executed** (archdocs lane's placement call).
6. **LICENSE:** keep both root + `fichero-engine/LICENSE` (the latter is required by `pyproject.toml`
   packaging). No action.

## Flags for Daniel (full list in PLAN §7)

MEMORY/HISTORY public-or-local · `rules.json` move-private · `project.yaml` gitignore · app-folder
rename name (`fichero/` recommended) · skills vendoring model + delete duplicated workflow-skills ·
release-skill `fichero-api`→`fichero-engine` fix-or-delete · `agent-work/*.py` script relocation ·
AGENTS.md incident-narrative trimming · whether to restore a GitHub-facing `docs/README.md`.

## Not done (by design)

No push. No structural changes beyond the Daniel-directed docs consolidation. No file moves/deletes
of root governance (all flagged for approval). No edits to docs-content-lane or archdocs-lane files.
