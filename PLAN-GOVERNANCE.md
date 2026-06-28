# PLAN-GOVERNANCE.md — Canonical Cleanup Plan for Going Public

**Worker:** opus REVIEW lane (`lane/review`, `~/code/fichero-worktrees/ms-review`)
**Date:** 2026-06-27
**Status:** REVIEW + PLAN + safe issue-harvest only. **No files moved/renamed/deleted.** Every structural change below waits for Daniel's approval before the IMPLEMENT phase.

**Coordination:** a concurrent `lane/docs` worker owns `site/docs/**`, `README.md`,
`RELEASE_NOTES.md`, `CONTRIBUTING.md`, `AGENTS.md` placement-rules, developer→contributor
rename, and the FAQ. This plan does **not** propose conflicting content edits to those
in-flight items — it covers the **higher-level structure, root-governance canonicalization,
the agent-harness/skills layer, and the `agent-work/` harvest**. Where a verdict touches a
docs-lane file, it is marked **[coordinate w/ docs lane]**.

---

## 0. The core tension

Fichero is going public/open-source, but the repo is also the live operating surface for an
autonomous agent team. Two facts collide:

1. `.claude/`, `.codex/`, `.ai/` were just made **private/gitignored** (commits `23b454ac`/`5c650276`).
2. But `STATE.md`, `MEMORY.md` (116 KB), `HISTORY.md` (205 KB), `HISTORY-worker.md`,
   `HISTORY/curator.md`, `rules.json`, and the whole `agents/skills/` + `docs/agent-workflow/`
   tree are **still committed and public** — and they read as internal agent scratch, not as
   docs a human contributor wants.

The job is to draw ONE clean line: **what a public contributor sees** (canonical, human-readable,
component-named) vs **what the agent team needs** (operational, can stay but clearly fenced or
made local). The decisions below all serve that line.

---

## 1. Decision table — root governance + top-level

| File / folder | Verdict | Rationale (one line) |
|---|---|---|
| `README.md` | **KEEP-AS-IS** [coordinate w/ docs lane] | Public front door; docs lane is already rewriting the prose/voice. Structure is right. |
| `CONSTITUTION.md` | **MAKE-CANONICAL** | Designate as THE product north-star (it already reads that way); fix one stale line (§Versioning still says "0.0.2 working line… day-to-day per worker/lane" — reframe for public). |
| `AGENTS.md` | **MAKE-CANONICAL (strengthen header)** | Daniel: the header framing is the canonical model — keep & strengthen it (see §2). It is the single operational doc; only trim agent-incident war-stories that read as internal. |
| `CLAUDE.md` | **KEEP-AS-IS** | Correct as a thin 6-line pointer to AGENTS.md. Exactly right. |
| `USER.md` | **MAKE-LESS-AI-SPECIFIC** → already largely done (PR #2695 reframed it) | Now reads as a public "about the author"; verify no internal agent-safety lines remain. KEEP. |
| `STATE.md` | **FLAG → keep committed but fence** | Load-bearing session-continuity (session-start/-end read+write it; CONSTITUTION names it the one local exception). Small, current. Keep — but see §6 flag on whether public. |
| `MEMORY.md` (116 KB) | **FLAG → MOVE or gitignore** | Append-only agent lessons log; load-bearing for the team but noise for a public contributor. Decision needed (§6). |
| `HISTORY.md` (205 KB) | **FLAG → MOVE→`agent-work/history/` or gitignore** | Giant dated session-log; pure internal narrative. Not something a contributor reads. Decision needed (§6). |
| `HISTORY-worker.md` (2 lines) | **DELETE(crud)** | A 2-line stale worker stub (last entry 2026-06-02). Superseded by per-lane HISTORY. |
| `HISTORY/` (dir, `curator.md`) | **MOVE→`agent-work/history/`** | Curator run-log; dated agent telemetry, belongs with agent-work history, not at repo root. |
| `RELEASE_NOTES.md` (286 KB) | **KEEP** [coordinate w/ docs lane] | Public Apple-style notes; docs lane owns content. Note size — see CHANGELOG overlap below. |
| `CHANGELOG.md` (13 KB) | **KEEP-AS-IS** | Keep-a-Changelog format; complements RELEASE_NOTES (dev-facing vs user-facing). Both are legit; document the split in CONTRIBUTING so they don't drift. |
| `CONTRIBUTING.md` | **KEEP-AS-IS** [coordinate w/ docs lane] | Correct, points to AGENTS.md + developer docs. Docs lane owns. |
| `LICENSE` | **KEEP-AS-IS** | MIT, correct. |
| `rules.json` | **MAKE-LESS-AI-SPECIFIC / FLAG** | Generic Claude-Code agent-guard allow/block policy — NOT Fichero-specific. See §4. |
| `project.yaml` | **FLAG → gitignore** | Auto-generated from Daniel's private `contexts.json` (room/omnifocus/people incl. `@handles`). Leaks personal workflow config; not useful to the public. Recommend gitignore. |
| `mkdocs.yml` / `requirements-docs.txt` | **KEEP-AS-IS** [coordinate w/ docs lane] | Docs-site build config; docs lane territory. |
| `icon.png` (910 KB) | **MOVE→`assets/`** | Loose 910 KB binary at repo root; belongs in `assets/` (which already exists). Cosmetic. |
| `.swiftlint.yml` / `.python-version` / `.traceignore` | **KEEP-AS-IS** | Standard tool config. |
| `.gitignore` | **MAKE-CANONICAL** | Already privatizes `.claude/.codex/.ai`; extend to whatever §6 decides (project.yaml, MEMORY/HISTORY). |

---

## 2. Proposed canonical governance doc-set (the ONE model)

Daniel's directive: the current `AGENTS.md` header **is** the canonical model. Keep and
strengthen it. The public-facing hierarchy:

```
README.md           → WHAT it is + how to run it           (humans, first contact)
CONSTITUTION.md     → product NORTH STAR: what/why/not/hard-constraints  (humans + agents)
CONTRIBUTING.md     → how HUMANS contribute                 (human contributors)
AGENTS.md           → THE single canonical agent/operational manual      (all agents)
   ├─ CLAUDE.md       thin pointer → AGENTS.md
   ├─ docs/CLAUDE.md  detailed architecture & dev guide (canonical, deep)
   └─ agents/skills/  per-lane jobs (session-start/-manager/-worker/…)
USER.md             → about the author (public "about")
```

**The canonical sentence to keep/strengthen at the top of AGENTS.md** (Daniel-approved):

> *AGENTS.md is THE single canonical agent/operational doc that Codex, Claude Code, and
> Claude-in-Xcode all read. `CLAUDE.md` is a thin pointer to it. `CONSTITUTION.md` is the
> product north-star. `docs/CLAUDE.md` is the detailed architecture/development guide.
> `agents/skills/` tell each lane its job.*

It already says almost exactly this (AGENTS.md:1-7) — the action is to **lock it as the
canonical contract** and make every other governance file's header defer to it (CLAUDE.md
already does; add the one-liner to CONSTITUTION.md and docs/CLAUDE.md so the chain is
explicit from any entry point).

### Where docs/ vs site/docs/ vs agent-work/ draw the line

| Tree | Audience | Rule |
|---|---|---|
| `site/docs/` | **Public** (users + contributors) | Published mkdocs site. The canonical *human* docs. Lives where the docs lane is consolidating. |
| `docs/` | **Contributors / deep internal** | Architecture deep-dives + operational runbooks (release lane, QA matrices, validation). NOT published as the main site. |
| `agent-work/` | **Agent team** | Dated proposals, handoffs, findings, loops. Working scratch — harvested for issues, kept as history, or deleted. Never the source of truth (GitHub Issues is). |

**The boundary problem found:** `docs/agent-workflow/` is agent scratch living in `docs/`, and
it **duplicates** `agents/skills/` (see §5). And `agent-work/` holds a lot of point-in-time
audits that belong as *history*, not as live docs. Net moves proposed:

- `docs/agent-workflow/` → its skill *docs* are stale duplicates of `agents/skills/` → **consolidate** (§5).
- `agent-work/proposals/*reality-check-*`, `*milestone-audit-*` → dated snapshots → **MOVE→`agent-work/history/`** (or delete; §3).
- Keep `docs/architecture/`, `docs/release/`, `docs/qa/`, `docs/CLAUDE.md` as the contributor-deep tier.

---

## 3. `agent-work/` cleanup plan

`agent-work/` holds **~110 files**: 69 proposals + dispatch/handoff/icanh-notes/notes/wireframes +
loose audits + two Python scripts. A prior `agent-work/proposals/2026-05-31-agentwork-review.md`
already harvested issues from the pre-2026-05-31 batch — so most actionable items are **already
filed**. The harvest below is deliberately lean (verify-net-new before filing).

### 3a. Three buckets

- **KEEP as dated history** → `agent-work/history/` (proposed new subdir): all `reality-check-*`,
  `milestone-audit-*`, the `2026-05-13-*` reviews, `2376-*`/`2375-*` triage, `digest.md`,
  `ISSUES-CREATED.md`, `post-collapse-review.md` — these are point-in-time snapshots, valuable as
  provenance but NOT live work and NOT issues.
- **HARVEST → GitHub issues** (filed this session; see §3c): only proposals that read as concrete,
  still-relevant, not-already-filed, not-obviously-done work.
- **DELETE(crud)**: one-off generated artifacts and superseded scratch (see §3b).

### 3b. Scripts in `agent-work/`

| File | Verdict | Rationale |
|---|---|---|
| `agent-work/classify_issues.py` (11 KB) | **DELETE(crud)** or MOVE→`scripts/` | One-off issue-classifier. If still run, move to `scripts/`; otherwise delete. FLAG. |
| `agent-work/kg_audit_runner.py` (44 KB) | **MOVE→`scripts/` or `fichero-engine/scripts/`** | Large reusable KG-audit tool; does not belong in scratch. FLAG which dir. |

### 3c. Issues harvested this session

A separate Explore pass triaged all ~110 `agent-work/` files. Result: **18 looked
"actionable", but on cross-check against open GitHub issues almost all are already
filed or are point-in-time snapshots.** The prior `agent-work/proposals/2026-05-31-agentwork-review.md`
already harvested the KG batch (communities/SPARQL/bio/Oxigraph), and the image-editing epic
(#462–469), graph-RAG chat (#1156), workflow regression harness (#1287), WebKit focus (#1346),
and the CLI plan (CLI is now **Live** per README) are all already tracked. The per-page
transcription fan-out finding (`icanh-notes/i13`,`i14`) is already **#2303** + **#2395**.

**Filed this session (verified net-new):**

| # | Title | Milestone | Source |
|---|---|---|---|
| **#2710** | [Workflows] Rationalize the transcribe-family presets — ≤4 canonical, shared config convention, per-page invariant | Workflows & Catalogue Hardening | `agent-work/icanh-notes/i15.md` + `i16.md` |

`#2710` is genuinely net-new: **#1794** consolidates the *Catalogue* family; nothing covered the
*Transcribe* family's 10-preset overlap + config inconsistency. The rest of the "actionable" set is
KEEP-HISTORY (audits/reality-checks/plans for already-filed work) or already an open issue — filing
them would be duplicate noise.

**The two `agent-work/` HTML wireframe mocks** (`wireframes/pairing-settings-mock.html`,
`mobile-device-mock.html`) and `proposals/2026-05-30-closed-issue-refile-log.txt` →
**DELETE(crud)** candidates (FLAG — they're harmless history; delete only if you want a clean tree).

---

## 4. `rules.json` — assessment

**What it is:** a generic **agent-guard allow/block/soft-deny policy** — the permission rubric a
sandboxed coding agent consults (read-only ops allowed, force-push/secret-exfil/public-surface
blocked, etc.). The `environment` block is all "None configured" placeholders. **Nothing in it is
Fichero-specific** — it's a vendored Claude-Code-style safety policy.

**Verdict: FLAG — three options for Daniel:**

1. **Move it private** → it's agent-harness config, same class as `.claude/.codex` which were
   just gitignored. Most consistent: move to the private vendor config and gitignore.
   **(Recommended.)**
2. **Keep public but relabel** → if kept, rename/headline it so a public reader knows it's the
   agent-safety policy (e.g. a top-level `_meta`/comment block, or `docs/agent-workflow/agent-guard-policy.json`)
   — currently a bare `rules.json` at repo root reads as app config, which it is not.
3. **Delete** → if the live guard policy lives in the private `.claude/` config and this is a
   stale copy. (Verify it isn't the canonical source before deleting.)

**Recommendation:** Option 1 (move private). It is not product, not docs, and not useful to a
public contributor; it's exactly the kind of agent-harness file the `.claude/.codex` privatization
was meant to fence off. **Do not delete until confirmed it isn't the live source.**

---

## 5. `agents/skills/` audit (Daniel's second task)

**Workflow we're matching against (Daniel's "how we work NOW"):** interactive tmux workers in
**isolated git worktrees** under `~/code/fichero-worktrees/`, each grinding a **milestone's GitHub
issues** and **committing as themselves**; the **manager** reviews + ponytail + build-gates +
`verify_all` + **merges via PR**, on a ~15-min loop.

**Key structural finding:** 5 of the 9 in-repo skills are **byte-identical copies** of the external
marketplace plugin `~/code/fichero-skills/plugins/fs_session/`. They are *vendored*, so they drift
(choose-next is already 10 lines behind external) and they are not the source of truth. The 4
repo-specific ones (build/release/gardener) have no external counterpart.

| Skill | Used now? | Up to date vs tmux-worktree model? | External source | Verdict |
|---|---|---|---|---|
| `session-start-worker` | ✅ yes (core lane) | ✅ mostly — "pick milestone issue, claim, commit referencing #, push branch, manager merges" matches. Generic/project-agnostic. | identical to `fs_session` | **KEEP** (re-sync from external on update; it's a vendored copy) |
| `session-start-manager` | ✅ yes (core lane) | ✅ aligned (coordinate/dispatch/no-product-code) | identical to `fs_session` | **KEEP** (vendored copy) |
| `session-end` | ✅ yes | ✅ aligned (updates STATE/MEMORY) | identical to `fs_session` | **KEEP** (vendored copy) |
| `dispatch-worker` | ✅ yes | ⚠️ **STALE base branch** — created worktrees off `0.0.2`, but `0.0.2` merged to **main** via #2652 on 2026-06-26. Also models **cherry-pick** integration vs the new **merge-via-PR** model. | identical to `fs_session` | **✅ EXECUTED** base branch `0.0.2`→`main` (safe/factual). **STILL FLAGGED:** cherry-pick→PR-merge reconciliation (judgment — leave for Daniel). |
| `choose-next` | ✅ yes | ⚠️ in-repo copy was **10 lines behind** external (36L→46L) | differs from `fs_session` (newer) | **✅ EXECUTED** — resynced from canonical `fs_session` source. |
| `fichero-build` | ⚠️ superseded | ❌ **STALE** — `cd fichero-api` + `.briefcase-venv` (dir renamed `fichero-engine`; build now via `fichero-engine/scripts/build_backend_bundle.sh` + `scripts/release-all.sh`) | none (repo-specific) | **✅ EXECUTED** STALE banner → `docs/release/release-lane.md`. **STILL FLAGGED:** full rewrite-vs-delete (unverifiable Briefcase flow — judgment). |
| `fichero-release-prep` | ⚠️ superseded | ❌ **STALE** — same `fichero-api`/`.briefcase-venv`; uses `scripts/build-release-dmg.sh` vs canonical `scripts/release-all.sh` | none (repo-specific) | **✅ EXECUTED** STALE banner. **STILL FLAGGED:** merge into release-lane runbook. |
| `fichero-release` | ⚠️ superseded | ⚠️ overlaps `docs/release/release-lane.md` + `create-github-release.sh` | none (repo-specific) | **✅ EXECUTED** STALE banner. **STILL FLAGGED:** reconcile to one source. |
| `gardener-agent` | ✅ yes (manager/cron) | ✅ accurate — `scripts/gardener.py` exists; flags/options match | none (repo-specific) | **KEEP** (no change) |
| `_shared/swift-principles.md`, `python-principles.md` | ✅ likely | spot-check vs `docs/architecture/` | n/a | **KEEP**, spot-check |
| `_shared/architecture-summary.md` | ❌ **ORPHANED** (no live skill references it) | ❌ **DEAD+STALE** — `fichero-swiftui/`, `fichero-api/`, `codex/restructure-api-swiftui` branch "43+ commits ahead of main", "NO AppKit", "LiteLLM" routing — all contradict current canonical docs | n/a | **DELETE candidate — FLAG** (orphaned dead file; not rewritten/deleted — deletes stay flagged). |
| `_shared/team-constitutions.md` | ❌ **ORPHANED** (no live skill references it) | ❌ **DEAD+STALE** — `~/code/fichero/fichero-swiftui/`, `fichero-api/`, `PYTHONPATH=fichero-api/src`, `xcodebuild test` (violates the no-xcodebuild-test hard rule), `sosumi MCP`, openclaw workspaces | n/a | **DELETE candidate — FLAG** (orphaned dead file; superseded by `session-start-*` skills). |

**Safe fixes EXECUTED this session** (factual/mechanical, live skills): `choose-next` resynced from
canonical `fs_session`; `dispatch-worker` base branch `0.0.2`→`main`; STALE banners added to the
three release/build skills pointing at `docs/release/release-lane.md`. **Still flagged (judgment
calls):** `dispatch-worker` cherry-pick→PR-merge model; full rewrite-or-delete of the release/build
skills; **delete the two orphaned dead `_shared` files** (`architecture-summary.md`,
`team-constitutions.md`).

**Sourcing recommendation:** the 5 `fs_session` skills should be treated as **vendored from
`~/code/fichero-skills`** — update the external source and re-copy, rather than editing in two
places. Decide (FLAG): keep vendoring copies into `agents/skills/`, or reference the plugin
directly? Vendoring keeps the public repo self-contained (recommended) but needs a re-sync step.

**`docs/agent-workflow/skills/` is a stale DUPLICATE of `agents/skills/`** — 21 markdown files
mirroring the session-start variants. This is agent-scratch in `docs/`. **Verdict: consolidate** —
`agents/skills/` (visible, canonical) is the source; `docs/agent-workflow/skills/` should either be
deleted or reduced to a one-line README pointing at `agents/skills/`. FLAG (don't execute).

---

## 6. Architecture-doc folder rename (Daniel's third task)

**Problem:** `docs/architecture/swiftui/` and `docs/architecture/api/` are named by **technology**,
not by **component**. Rename to match the actual components:

| Current | Proposed | Component |
|---|---|---|
| `docs/architecture/swiftui/` | `docs/architecture/<app-name>/` (see pick below) | the SwiftUI app (`fichero/`) |
| `docs/architecture/api/` | `docs/architecture/fichero-engine/` | the FastAPI server (`fichero-engine/`) |
| `site/docs/architecture/swiftui/` | same rename [coordinate w/ docs lane] | published mirror |
| `site/docs/architecture/api/` | same rename [coordinate w/ docs lane] | published mirror |

**App-folder name — RECOMMENDATION + FLAG:**

> **Recommend `docs/architecture/fichero/`** — rationale: the app's actual on-disk component is
> `fichero/` and the Xcode project is `fichero/fichero.xcodeproj`, so `docs/architecture/fichero/`
> mirrors the source tree 1:1 and reads cleanly to a contributor. The engine is `fichero-engine/`
> → `docs/architecture/fichero-engine/`. Symmetric: **`fichero/` (app) + `fichero-engine/` (server)**.

> **FLAG for Daniel** — alternatives if you want the tech disambiguated in the doc tree:
> `fichero-swiftui/` (clear it's the Swift client) or `fichero-swiftui-client/` (most explicit, but
> longer and "client" slightly undersells that the app is a full surface). My pick stays `fichero/`
> for source-tree parity; choose `fichero-swiftui/` if you prefer the doc folder to self-describe
> the stack.

**Rename is mechanical but touches ~48 references — do NOT execute yet.** Internal links that need
updating when the rename lands (counted this session):

- **`docs/architecture/swiftui` → ~35 references** across: `AGENTS.md`, `CLAUDE.md`-chain docs,
  `mkdocs.yml`, `MEMORY.md`, `STATE.md`, `HISTORY.md`, `docs/ROADMAP.md`, `docs/README.md`,
  `docs/CLAUDE.md`, `docs/architecture/overview.md`, `docs/architecture/node_model_fold_staging.md`,
  `fichero/README.md`, `fichero/AGENTS.md`, `site/docs/developer/README.md`,
  `site/docs/architecture/overview.md`, **plus ~10 `scripts/check_*.py` guard scripts** that grep
  these paths (`check_swift_transport.py`, `check_view_endpoint_access.py`, `check_appkit_imports.py`,
  `check_observer_pattern.py`, `check_openapi_shadow_types.py`, `check_model_download_location.py`,
  `check_swift_hand_rolled_urls.py`), **and several Swift source header-comments**
  (`Models/WorkflowExecutionStore.swift`, `Models/LibraryManager.swift`, `Models/ObservableDomainStore.swift`,
  `Views/Library/*.swift`) and `fichero-engine/src/fichero/api/change_stream.py`.
- **`docs/architecture/api` → ~13 references** (subset of the above files + `docs/CLAUDE.md`,
  `AGENTS.md` "Before editing backend" section).

**IMPLEMENT-phase checklist (when approved):** `git mv` the two dirs (×2 for site mirror), then a
single `grep -rl 'architecture/swiftui'` / `architecture/api` sweep updating every hit above, then
re-run the `scripts/check_*` guards to confirm none break on the path change, then `mkdocs build`.
**[coordinate the `site/docs/architecture/` half with the docs lane.]**

---

## 6b. Canonical docs consolidation — **EXECUTED this session** (Daniel-directed)

Daniel's decision: mkdocs should render the **actual `docs/` folder**, not a separate `site/docs/`.
**ONE `docs/` folder** that is both what mkdocs publishes AND what agents+people read. This was
the one structural change Daniel told me to *execute* (I own docs structure; the docs-content and
archdocs lanes run in parallel; the manager reconciles at merge with this structure canonical).

**What I did (committed on `lane/review`, not pushed):**

1. **Merged curated `site/docs/` → `docs/`** (history-preserving `git mv`): `index.md`, `faq.md`,
   `how-its-built.md`, `user/`, `api-reference/`, `assets/`, and the 8 `developer/` pages (merged
   into the existing `docs/developer/`, which only had `cli-test-harness.md` — no collisions).
2. **Architecture:** `site/docs/architecture/overview.md` was identical to `docs/architecture/overview.md`
   → dropped the duplicate. The 3 *differing* published overviews (`api/overview.md`,
   `swiftui/overview.md`, `release-process.md`) were **parked in `agent-work/docs-reconcile/`** with a
   README so the **archdocs lane** can reconcile them into the canonical `docs/architecture/` tree
   (I did not silently overwrite or lose them). Nav now points at the `docs/architecture/` versions.
3. **Moved agent scratch OUT of `docs/` → `agent-work/`** (per Daniel: session notes, qa, reviews,
   validation, morning-test, orphan-triage): `docs/qa/`, `docs/reviews/`, `docs/VALIDATION.md`,
   `docs/VERIFY.md`, `docs/MORNING-TEST.md`, `docs/orphan-triage-report.md`, `docs/agent-workflow/`
   (also resolves the skills-duplication in §5), `docs/superpowers/`, `docs/archive/` (→`docs-archive/`),
   `docs/design/` (→`docs-design/`).
4. **`mkdocs.yml`:** `docs_dir: site/docs` → `docs`; `edit_uri` → `edit/main/docs/`; `site_dir`
   → `_site_build`; rewrote the header comment. Nav paths unchanged (they resolve under `docs/`).
5. **Removed stale `docs/README.md`** — it conflicted with the new `docs/index.md` (mkdocs strict
   error) and its links pointed at the now-moved `../site/docs/` paths. `index.md` is the canonical
   home. **FLAG (docs-content lane):** if you want a GitHub-folder-facing `docs/README.md` distinct
   from the site home, add a short fresh one — don't restore the old broken one.
6. **`scripts/deploy-site.sh`** + **`.gitignore`** updated for `_site_build` / `docs_dir: docs`.
7. **`agent-work/` stays separate and is never rendered.**

**Gate: `mkdocs build --strict` → EXIT 0 (clean).** `site/` directory removed (was only `site/docs/`).

**Dangling `site/docs/` references that the content/archdocs lanes own** (I did NOT edit these to
avoid conflicting with in-flight lane work — FLAG for manager reconciliation): `README.md`,
`USER.md`, `CONTRIBUTING.md`, `fichero-engine/README.md`, `fichero-engine/AGENTS.md`, and the two
stale release skills (`fichero-release`, `fichero-release-prep`, already flagged §5). A mechanical
`site/docs/` → `docs/` sweep across those closes them out.

## 6c. LICENSE files — assessment (Daniel-requested)

Only **two** LICENSE files exist (no `fichero/LICENSE`): root `LICENSE` and `fichero-engine/LICENSE`
— **byte-identical** MIT. `fichero-engine/pyproject.toml:22` declares `license.file = "LICENSE"`
(PEP-621), so the **engine copy is required by the Briefcase/packaging build** — do NOT remove it.

**Verdict: KEEP BOTH.** Root `LICENSE` is the canonical repo license; `fichero-engine/LICENSE` is a
required packaging artifact. No `fichero/LICENSE` to worry about. **No action needed.** (If you ever
want a single source, symlink or a build-time copy step could dedupe — but that's churn for no real
gain; two identical MIT files is fine and conventional for a packaged sub-component.)

## 7. Flags for Daniel — decisions needed before IMPLEMENT

1. **MEMORY.md (116 KB) + HISTORY.md (205 KB):** keep committed (transparency / "built in the
   open"), or **gitignore / move to `agent-work/history/`** for a clean public repo? They are
   load-bearing for the agent team (session-start/-end read+write), so they can be *local-only*
   but not deleted. **Recommend:** keep `STATE.md` public (small, current); move the two giant
   append-logs under `agent-work/history/` and/or gitignore the churn ones. **Your call on public-ness.**
2. **`rules.json`:** move private (recommended), keep-but-relabel, or delete? (§4)
3. **`project.yaml`:** gitignore (recommended — leaks `contexts.json` personal config + `@handles`)?
4. **App-folder rename name:** `fichero/` (recommended, source-parity) vs `fichero-swiftui/` vs
   `fichero-swiftui-client/`? (§6)
5. **Skills sourcing model:** keep vendoring `fs_session` skills into `agents/skills/`
   (recommended, self-contained), or reference the external plugin? And do you want
   `docs/agent-workflow/skills/` deleted (it duplicates `agents/skills/`)? (§5)
6. **Release skills + dead `_shared`:** STALE banners are in place. Decide: fully rewrite
   `fichero-build`/`fichero-release*` to the current `scripts/release-all.sh` lane, or **delete**
   them and defer entirely to `docs/release/release-lane.md`? And **delete the two orphaned dead
   `_shared` files** (`architecture-summary.md`, `team-constitutions.md` — referenced by no skill,
   contradict canonical docs)? (§5)
7. **`agent-work/*.py` scripts:** `kg_audit_runner.py` → `scripts/` or `fichero-engine/scripts/`?
   `classify_issues.py` → keep (move to scripts/) or delete? (§3b)
8. **AGENTS.md war-stories:** the operational manual embeds dated incident notes (e.g. the
   `rm-deleted fichero-search` story in dispatch-worker, `#2538`/`#760` asides). Keep for hard-won
   context, or trim the ones that read as internal-only for the public version? (Recommend: keep
   the *rules*, move the *incident narratives* to MEMORY/history.)

---

## 8. Out of scope (owned by the docs lane — listed for coordination, not actioned here)

README voice, RELEASE_NOTES content, CONTRIBUTING wording, developer→contributor rename, FAQ, and
`AGENTS.md` placement-rules prose. This plan defers content edits to those files. **Note:** the
`site/docs/` → `docs/` *structural* consolidation was executed this session (§6b) per Daniel's
direct instruction (I own docs structure); the **content** inside the moved files is untouched and
remains the docs/archdocs lanes' to edit — the manager reconciles at merge with this structure
canonical. The architecture-folder *rename* (swiftui→fichero, api→fichero-engine; §6) remains
**flagged, not executed** — it's the archdocs lane's placement call.
