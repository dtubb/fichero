# Bugtriage dispatch — 2026-05-30

Your prior session's output (`agent-work/proposals/2026-05-30-issue-triage.md`) is the plan. Execute it + the additions below. No code edits — `gh` CLI + plan documents only. **Worktree:** `~/code/fichero-0.0.2`. **Branch:** `0.0.2`.

## 0. CORRECTION — Milestones IS the canonical organization

Original triage doc proposed bulk-migrating issues to Project #5 with Epic field. **Replace that approach.** The repo has 45 open milestones that already group issues by feature + version (Daniel reviewed the Milestones view 2026-05-30 and finds it useful). Project #5 stays as a curated 30-item focus board — do NOT auto-add 248 issues to it.

**The real cleanup is on milestones:**

Manager already done: Epic + Priority fields added to Project #5; closed 5 dupes (#475, #423, #1303, #1326, #1217); labeled ~44 roadmap stubs with `roadmap`.

**Keep (active milestones):** `0.0.2`, `0.0.3 - KG Navigation + Polish`, `0.0.3 - Post-LLM-stack`, `0.0.4 - Local RAG`, `Search v1`, `Spatial Knowledge Layer`, `Image Editing: Crop + Rotate`, `Hermeneutics`, `Backend Ops + Migrations`, `Search: Hybrid Retrieval`, `0.0.3 - Image Editing v2`, `0.4.3 - Wire: Export Web + Netlify`, `0.3.2 - Wire: Image Segmentation`, `Integrations`, `API Security + Auth`, `Export: JSON + Markdown`, `Epistemic Platform Expansion`.

**Retire (close + move open children to closest live milestone):**
- `0.7.1 - Wire: Research Agents` → Researcher epic / `0.0.4`
- `0.7.0 - Wire: Agents` → Researcher epic
- `0.6.1 - Wire: Spatial Library` → `Spatial Knowledge Layer`
- `0.5.0 - Wire: MCP Servers` → `0.0.3 - KG Navigation + Polish`
- `0.4.2 - Wire: Export Spreadsheets` → `Export: JSON + Markdown`
- `0.4.1 - Wire: Export Documents` → `Export: JSON + Markdown`
- `KG Predictions` → `Epistemic Platform Expansion`
- `Epistemology Graph`, `Ontology Browser`, `KG Claim Inspector`, `KG Claims List`, `KG Entities` → `0.0.3 - KG Navigation + Polish`
- `Automation` → `0.0.4 - Local RAG`
- `Activity Monitor` → `0.0.2` if children are active, else `0.0.3`
- `Batch Processing` → `0.0.3 - Post-LLM-stack`
- `Workflow Chains`, `Workflow Editor`, `Workflow Tools`, `Workflow Basics` → fold into new milestone `Workflows v1` or `0.0.3 - Post-LLM-stack`
- `Chat v1`, `Chat v2: Model Comparison` → Researcher epic
- `Local Models` → `0.0.4 - Local RAG`
- `Search v2: Filters + Layouts`, `Search v3: Semantic Map` → `Search v1` or `Search: Hybrid Retrieval`
- `Providers + API Keys` → KEEP only if there's active work; otherwise retire and move 12 open issues to `0.0.3` settings work.

**Mechanics:**
```bash
# Move open issues from a milestone to a destination
for n in $(gh issue list --milestone "<source-milestone>" --state open --json number -q '.[].number'); do
  gh issue edit "$n" --milestone "<destination-milestone>"
done
# Then close the source milestone
gh api repos/dtubb/fichero/milestones/<id> -X PATCH -F state=closed
```

**Then proceed with §1.** §1's "add three custom fields" step is already done; you only need the dupe-close + bulk-Epic-tag-on-Project-#5 steps. Add only the ~30 currently-on-project items to Epic field; do NOT bulk-import all 248 issues.

## 1. Apply Phase 1 (GH hygiene) from your own plan

From `agent-work/proposals/2026-05-30-issue-triage.md` §7 ("GitHub Projects v2 Reorganization Proposal"):

- Add three custom fields to Project #5 "fichero" (Epic / Status / Priority, single-select, options as listed).
- Close as duplicates with cross-reference comments: **#1327 → #1338**, **#475 → #1334**, **#423 → #375**, **#1303** (env, not code), **#1326 → #1318**.
- Verify+close **#1217** (fix landed in `73856f0d`).
- Bulk-label `roadmap`/`parking-lot` and hide from board: release-gate stubs #488–#515 + #511 #512 #505–#508; future #740, #657, #1092–#1095, #1158–#1161, #374, #375, #378–#380, #461.
- Retire feature-based milestones with 0 closed issues (close with no-further-work note): list in §7 of your plan.
- Keep version milestones: `0.0.2`, `0.0.3 - KG Navigation + Polish`, `0.0.3 - Post-LLM-stack`, `0.0.4 - Local RAG`.
- Bulk-set Epic field per your mapping table.

## 2. Incorporate Daniel's running notes (additions to the plan)

Tag/audit/file as you go:

- **#874** — User-extensible entity types. Daniel says this was `in_progress` in TASKS. Check current state (grep merged PRs, look at TASKS.md task #264, scan `fichero-engine/src/fichero/api/routes/registries.py` + Swift `EntityTypeRegistry`). Either close as done if shipped, or leave open with a short status comment + tag Epic=KG-Single-Path (closest fit) or new Epic=Curation/Settings.
- **#1229** — Reading-surface / toolbar polish. Tag Epic=Onboarding (or new "Inspector-UX"); Priority=P1.
- **#1230** — XCUITest click-through UI test target. Tag Epic=Infrastructure; Priority=P2 (gated by [[feedback_xcuitest_tcc_automation_grant]]).
- **#1231–#1239** — release-data imports. Tag Epic=Importers for #1231 #1232 #1233 #1234 #1235 #1236 #1238; Epic=Importers + sub-tag "xlsx" for #1237; Epic=Infrastructure for #1239 (remote ACENET SSH).
- **#1054** — Search returns every page, needs relevance threshold. Tag Epic=Search-or-new; Priority=P1 (Daniel listed it pending-not-started).
- **#1151** — xfail gated-router tests. Tag Epic=Infrastructure; Priority=P2.

## 3. Release-task housekeeping (Daniel's call: separate repo/issue)

Tasks #157–#165 are notarize/DMG/Sparkle/publish flow. Daniel says these "belong in a separate repo/issue, so can probably be closed or moved." Options:
- **Recommend** option A: open a single tracking issue in `dtubb/fichero-releases` titled "0.0.2 release flow — notarize/DMG/Sparkle/publish" with checklist mirroring tasks #157–#165, link back, then close all 9 tasks in this repo's TASKS.md.
- Document your recommendation in a new section appended to `agent-work/proposals/2026-05-30-issue-triage.md`, but **do not** open/close them yet — wait for Daniel's explicit go.

## 4. Output

Append your work to `agent-work/proposals/2026-05-30-issue-triage.md` under a new `## Execution Log — <timestamp>` section: for each mutation, list `gh` command run + result. Commit + push to `0.0.2`. Comment on each issue you close with the duplicate ref.

**Gate rule:** never `gh issue close` until you've grep-confirmed the merge (`git log origin/main..HEAD | grep "(#N)"`) — see [[feedback_lane_orchestration_lessons]] §4.

When done, write a one-line summary to `agent-work/dispatch/2026-05-30-bugtriage-DONE.md` so the manager can pick it up.

## 6. Re-file closed issues from retired version milestones (2026-05-30 addition)

The 4 version milestones are now closed (`0.0.1`, `0.0.2`, `0.0.3`, `0.0.4`) but their ~593 closed issues are still tagged to them. Going forward, NO version milestones — releases are dated git tags + `dtubb/fichero-releases` entries. So:

1. **For each closed issue on a version milestone**, infer its feature area from the title + body and apply the right feature milestone. Use the milestone descriptions in `docs/agent-workflow/github-conventions.md` as the rubric.
2. **Closed-without-milestone issues** (also several thousand): same heuristic; tag the ones whose feature area is obvious from title. Drop the others — they're closed and unlabeled forever.
3. **Once all the closed issues are off the version milestones**, delete the 4 version milestones (`0.0.1`, `0.0.2`, `0.0.3`, `0.0.4`).
4. **Delete the legacy labels** that have zero remaining issues (after manager's open-issue label migration completes — confirm with `gh label list` and check each has 0 issues before delete).
5. **Remove the "Migration table" section** from `docs/agent-workflow/github-conventions.md` once 4+5 are done. Commit message: `docs(gh-conventions): remove migration scaffolding`.

**Approach:** batch by feature-area; pull all closed issues with title regex match, bulk-apply. Don't try to be perfect — 80% accuracy beats 100% effort on 6000+ issues. Log decisions to `agent-work/proposals/2026-05-30-issue-triage.md` under a new `## Closed-Issue Re-filing Log` section.

**Hard rule:** never modify the CONTENT of closed issues. Milestone + label only.

## 7. License to add new feature milestones (2026-05-30 addition)

When re-filing closed issues you may find a coherent feature area that has no milestone yet. Examples Daniel flagged:
- **API / OpenAPI Contract** — the typed round-trip between Python and Swift, contract tests, `sync_openapi_schema.sh` machinery, OpenAPI generator output. Currently lives in Infrastructure but might warrant its own milestone given how many issues touch it.
- **Endpoint / Interface design** — Daniel mentioned this gesturally; if you see a coherent cluster of issues about API surface design (not implementation), create a milestone for it.

Rules for adding a milestone:
1. At least 5 closed issues or 2 open issues clearly belong to it.
2. The scope is distinct from existing milestones (won't be folded back in).
3. Write a one-line description on the milestone before tagging issues to it.
4. Log the creation in `agent-work/proposals/2026-05-30-issue-triage.md` under your execution log.

Otherwise — fold issues into the closest existing milestone. Don't overgrow the milestone set; the point is fewer, clearer buckets.

## 8. Backfill labels on unlabeled issues (closed + open)

While re-filing closed issues to feature milestones, also apply labels to **any issue (open or closed) that has zero labels**. Many closed issues from before the canonical label set existed have nothing — they should at least have `type:*` + a milestone tag.

```bash
# Find unlabeled
gh issue list --state all --limit 500 --search "no:label" --json number,title,state \
  -q '.[] | "\(.number)|\(.state)|\(.title)"'
```

Minimum backfill per issue:
- `type:bug` / `type:feature` / `type:task` — infer from title verb (fix/add/update/refactor/clean)
- Milestone — from the new canonical set
- If you can't tell, mark `type:task` + closest-fit milestone; better to be roughly right than to skip.

This is a one-shot pass; future issues should be labeled at file time (the new conventions doc tells filers what to apply).

## 9. Milestone naming clarifications (2026-05-30 final)

- **Importers** = the import TOOLS (Kreuzberg/Docling loaders, Box/Dropbox/XLSX/drag-in, remote SSH backend). Mechanism.
- **Source Archives** = the specific source COLLECTIONS being ingested (Chota Valley maps, Archivo Judicial, Mosquera notebooks, etc.). Content. Each issue typically references a single named corpus.
- Don't mix them. A bug in the XLSX import path = Importers. A request to ingest the Mosquera notebooks = Source Archives.

## 10. Release-flow issues

If you find any issue about Sparkle / DMG / notarization / appcast hosting:
- If it's app-internal (in-app auto-update behavior) → **App Shell** milestone + `release-gate` label
- If it's distribution-pipeline (hosting the appcast, GH release, signing infrastructure) → cross-reference `dtubb/fichero-releases#1` in a comment, then close as moved
- Avoid creating a "Release" milestone in this repo — that lives in `dtubb/fichero-releases`.
