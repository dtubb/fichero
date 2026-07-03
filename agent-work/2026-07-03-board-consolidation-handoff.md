# Session-end handoff — Board consolidation + review-EPIC breakdown (2026-07-03)

Board organizer (Opus). All work is on the GitHub board (`dtubb/fichero`) + one
committed doc change. **Nothing pushed.**

## 1. Milestones consolidated
- **Closed 6 empty milestones** (verified `open_issues==0` via `gh api` first):
  #65 Source Archives · #78 Native SwiftUI Controls · #82 Test Coverage ·
  #83 AI Infrastructure · #101 Networking (OpenAPI-only) · #108 Docs Review.
  → 36 → **30 open milestones**.
- **Re-dated all 30** so `due_on` ascends = Daniel priority. Spine:
  #109 (07-05) → #110 (07-09) → #111 (07-14) → #112 (07-22) → #113 (07-28) →
  #105 (08-03) → big backlogs #60/#55/#17/#22/#54/#53 (Aug–Sep) → client/infra
  tail → far future #114 tvOS (2027-02-15), #95 visionOS (2027-03-15).

## 2. Labels collapsed (~42 → 15)
- lane: `backend` · `client:swiftui` · `docs` (renamed from `documentation`)
- type: `type:feature` · `type:bug` · `type:task`
- kept (selector-critical): `status:in-progress/blocked/ready-for-test`,
  `priority:P0–P3`, `needs:human`, `needs-design`
- remapped→deleted: `type:test→type:task`, `ready-for-test→status:ready-for-test`,
  `mcp→backend`
- deleted redundant: `roadmap`, all `tier:*` (computed dynamically by
  `dispatch_advisor.py`), all `area:*`, all `phase:*`, `client:cli`/`client:html`

## 3. ROADMAP synced to the milestone spine
`scripts/choose_next.py` orders by `docs/ROADMAP.md` tiers, NOT `due_on`. Appended
a machine-read **`## Tier` PRIORITY SPINE** (13 tiers, milestone titles matching
GitHub exactly, in due-date order) + a top pointer — additively (4-phase design
narrative preserved). Verified: self-test passes, 13 tiers parse, live run returns
**Tier 1 — Dev & Build Harness (#109)** as next work. Commit `b6df6015` (Claude).

## 4. Review EPICs broken into sub-issues
Shared keystone (first sub-issue of each) = **route through the audited action
registry #1848 under a real per-user token.**

- **#2884 CLI hardening** (Developer Experience): keystone **#2888**, then #2889
  (login/--as-user), #2890 (typed flags), #2891 (canonical nouns), #2892 (dead SDK
  + completion), #2893 (SSE/--json).
- **#2882 MCP** (Chat & Agent): keystone **#2895**, then #2896 (collapse 3 servers →
  one generated-from-registry), #2897 (expose writes, retire dead mcp_full.py),
  #2898 (cleanup).
- **#2883 fichero-web** (Exporter — moved out of iOS/iPad Embedding; a browser
  client is not iPad app embedding): keystone **#2899**, then M1–M5 #2900–#2904.

Each EPIC body now carries a sub-issue checklist. Keystones tagged
`needs-design` + `priority:P1` (auth-perimeter, gate the rest).

## 5. Agent EPIC links
- **#2886** (embedded WebKit + Safari MCP, STP 247) and **#2887** (pluggable agent
  harness pi/claude/codex/gemini) → set to the **Researcher** milestone (where
  #2067 lives), added to #2067's sub-issue list, cross-link comments both ways.

## Open questions for f_manager
1. **Middle-tail milestone order** (Tiers 8–12, positions 13–48) is my judgment —
   confirm or hand me a different order and I'll re-date.
2. **fichero-web (#2883)** parked in Exporter — confirmed keep, but a dedicated
   *Web Client* milestone may be cleaner later.
3. **`needs-design`** kept as a gate (not lane/type) — leave as-is?

## Standing role
Single point for new issues/milestones. When the manager needs an issue filed,
it comes here. `choose_next.py` spine + board `due_on` must stay in sync —
this doc + the ROADMAP `## Tier` block are the source of truth for "what next".
