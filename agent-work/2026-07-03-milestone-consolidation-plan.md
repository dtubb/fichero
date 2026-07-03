# Milestone Consolidation Plan — 2026-07-03

Read-only research; this is the only file written. No milestone/issue was modified while producing it.
Data pulled live via `gh issue list --milestone "TITLE" --state all` and `gh api repos/dtubb/fichero/milestones/N` /
`gh api repos/dtubb/fichero/issues?milestone=N` for every closed milestone, every open milestone with
<5 open issues, and the specific duplicate-suspect pairs named in the brief. Milestone #1 does not exist
(404 — the truncated note in the brief was a red herring; ignore it).

---

## 1. Inventory

### OPEN milestones (54)

| # | Open | Closed | Title | Scope (one line) |
|---|------|--------|-------|-------------------|
| 12 | 15 | 24 | Mind Palace | Mind Palace / Spatial Knowledge Layer — RealityKit 3D library view |
| 13 | 18 | 46 | Image Editing | Non-destructive image editing: crop, rotate, enhance |
| 14 | 21 | 7 | Exporter | Library/folder/document export to Word/PDF/Excel/JSON/Markdown/static HTML |
| 17 | 15 | 31 | Search | Hybrid BM25 + dense retrieval |
| 20 | 20 | 52 | Settings & Providers | Settings: AI provider management |
| 22 | 5 | 14 | Chat | First-party chat surface |
| 52 | 3 | 8 | MCP | MCP server surface for outside agents (confirmed: #1439, #509, #270 open) |
| 53 | 32 | 10 | Researcher | Agentic research surface |
| 54 | 15 | 139 | Workflows | Workflow editor |
| 55 | 45 | 242 | KG & Hermeneutics | Typed entity layer, CRUD |
| 56 | 17 | 25 | Activity & Automation | Activity Monitor + Automation |
| 57 | 14 | 45 | Importers | Import tools and loaders |
| 60 | 91 | 159 | Library & Reading Surface | Multi-pane reading surface |
| 62 | 11 | 60 | Mac App Shell | The macOS app chrome |
| 64 | 14 | 51 | Developer Experience | Everything for people BUILDING Fichero — docs+tooling+CLI hardening (confirmed: absorbs CLI epic #2884) |
| 66 | 2 | 2 | Website | tubb.ca/fichero — public website (confirmed: #1873, #665 open) |
| 67 | 3 | 1 | Documentation | End-user + developer manual (confirmed: #2692, #1797, #1705 open) |
| 68 | 3 | 9 | Bibliography & Citations | References/citations management (confirmed: #1589, #974, #924 open) |
| 70 | 7 | 36 | API Surface & Test Harness | Make the engine reachable+testable+sync-verified |
| 71 | 18 | 34 | Window Chrome & Toolbars | Main toolbar de-duplication |
| 73 | 13 | 3 | Curation | Human curation: multi-select disable/group/delete/merge/unmerge/reclassify |
| 74 | 8 | 13 | Remote & Self-Hosting | Engine may run remotely |
| 75 | 4 | 0 | Sharing & Collaboration | Share button + share-as-link (confirmed: #2054, #2029, #2021, #1867 all open) |
| 76 | 2 | 0 | Notifications & Watchlist | System notifications + watchlists (confirmed: #1870, #1869 open) |
| 77 | 4 | 17 | Observable Data Layer | (null desc) |
| 79 | 3 | 2 | Mac Polish — Fonts, SF Symbols, No Emoji | (confirmed: #1969, #1951, #1929 open) |
| 81 | 8 | 10 | Multiplatform — iOS/iPadOS/Mac | Adaptive Apple UI shell work |
| 84 | 2 | 0 | Source Archive - ICANH | Corpus-specific ICANH/Andagoya (confirmed: #2464, #2208 open) |
| 85 | 3 | 1 | Source Archive - Marshall Diaries | Corpus-specific Newton C. Marshall diary (confirmed: #1798, #1708, #1667 open; #1236 closed) |
| 88 | 1 | 0 | Source Archive - Archivos Nuestros | Corpus-specific Archivos Nuestros (confirmed: #2209 open) |
| 89 | 2 | 1 | Source Archive - Maps of the Black Pacific | Corpus-specific maps (confirmed: #1654, #1331 open; #1232 closed) |
| 90 | 1 | 24 | AI Backend Hardening | Opus-review-driven hardening of AI backend (confirmed: #2615 open; 24 closed hardening-bug issues) |
| 91 | 3 | 63 | Workflows & Catalogue Hardening | Opus-review-driven hardening of default workflows (confirmed: #2526,#2524,#2445 open) |
| 92 | 1 | 12 | Programmatic Guardrails | Machine-enforce the design brief (confirmed: #2271 EPIC open) |
| 93 | 7 | 18 | UI Reform — Representations | Alternative representation views (confirmed: #2807,#2755,#2670,#2667,#2481,#2474,#2467 open) |
| 94 | 4 | 16 | UI Reform — Inspector & Annotation | Modular/floating inspectors (confirmed: #2661,#2458,#2455,#2255 open) |
| 95 | 9 | 0 | visionOS — Apple Vision Pro port | Port Fichero to visionOS |
| 96 | 13 | 13 | Device Pairing & Discovery | Mac-hosted engine discovery, QR/code pairing |
| 97 | 4 | 2 | Archive Capture — Mobile & Camera Intake | Post-Device Pairing capture intake (confirmed: #2380,#2355,#2353,#2352 open) |
| 98 | 3 | 1 | Archive Capture — Automation & Provenance | Workflow automation for captured images (confirmed: #2358,#2357,#2356 open) |
| 99 | 4 | 0 | Watched-Entity Research Agents | Watch names/places/entities/terms (confirmed: #2363,#2362,#2361,#2360 open) |
| 100 | 4 | 0 | Clip Service — Web & Document Capture | Capture web pages/URLs/documents (confirmed: #2367,#2366,#2365,#2364 open) |
| 102 | 14 | 6 | Chat & Agent | In-app chat + agentic control surface |
| 103 | 24 | 13 | Repo Hygiene & Structure | Repo cleanup, restructure, docs, onboarding |
| 104 | 1 | 3 | SwiftUI App Structure & Naming | Reorganization of fichero/fichero/ (confirmed: #2571 open) |
| 105 | 13 | 5 | iOS/iPad Embedding & Multi-Library | Embedding Python engine on iPad + multi-library |
| 106 | 3 | 1 | Release & Distribution | Shipping Fichero: signing/Sparkle/dated releases (confirmed: #2583,#2582,#2581 open) |
| 107 | 4 | 14 | Node Model & Endpoint Unification | Collapse 'one feature=one subsystem' sprawl into node model |
| 109 | 3 | 1 | Dev & Build Harness | Reproducible debug/test/release/testflight build+launch |
| 110 | 2 | 3 | Connection & Startup Bulletproofing | Bulletproof app connection path (confirmed: #2861,#2859 open) |
| 111 | 3 | 1 | Multi-user & Shared Libraries | Multi-user sharing UX + per-library access (confirmed: #2869,#2868,#1847 open) |
| 112 | 1 | 1 | iOS/iPad/Mac UX | iPhone/iPad/Mac interaction model (confirmed: #2865 open) |
| 113 | 1 | 0 | Import & Index Modes | copy/move/link/index import modes (confirmed: #2876 open) |
| 114 | 1 | 0 | tvOS — Apple TV port | Apple TV target (confirmed: #2878 open) |

Note: milestone #1 does **not exist** (`gh api .../milestones/1` → 404). The brief's truncation note is moot — drop it.

### CLOSED milestones (11)

| # | Open | Closed | Title | Verified current state |
|---|------|--------|-------|-------------------------|
| 11 | 0 | 247 | Infrastructure | Fully closed. Grab-bag of ~247 issues spanning auth/security-hardening, DB/concurrency, workflow/KG bugs, CLI polish, SwiftLint, release gates 0.0.1-0.0.3. All 247 read — genuinely done work (bug-fixes/features shipped), not a live theme anymore. Its *themes* now live on: Security(closed,#69), AI Backend Hardening(#90), Workflows&Catalogue Hardening(#91), Developer Experience(#64), API Surface & Test Harness(#70). |
| 63 | 0 | 2 | CLI | Only 2 issues (#1351, #1348 — both stale-test fixes), both closed. The CLI *theme* is NOT done — EPIC #2884 (CLI hardening: importers bypass HTTP, opaque write flags, duplicate command trees) plus 7 sibling issues (#2893,#2892,#2891,#2890,#2889,#2888,#2884) now live in Developer Experience #64. Confirms brief's suspicion. |
| 65 | 0 | 3 | Source Archives | Umbrella emptied by moving each issue to its own per-corpus milestone (#1234→ICANH is actually still in Source Archives itself per data below (Medellin has no dedicated milestone); #1238 Istmina also parked here; #1231 slipbox also here). See §3. |
| 69 | 0 | 20 | Security | Fully closed, 20 issues, all genuinely fixed CVE-class bugs (RCE/SSRF/auth/ACL). But the **theme** is not over: Connection & Startup Bulletproofing #110 and Multi-user & Shared Libraries #111 carry the *next generation* of auth/session/device-security work (#2861 EPIC, #2869 EPIC). Correctly closed as a historical batch; NOT a duplicate to fold — new work correctly lives in #110/#111, not reopened here. |
| 78 | 0 | 1 | Native SwiftUI Controls | 1 issue (#1912, a guardrail), closed. Theme is live and split across Mac Polish #79 (fonts/SF Symbols/no-emoji/status-redesign) and UI Reform #93/#94 (representation + inspector rebuilds using native controls). Correctly closed as a historical batch — new native-control work correctly routes to #79/#93/#94, don't reopen #78. |
| 82 | 0 | 26 | Test Coverage | 26 auto-filed `scan_test_coverage_gaps.py` issues (all closed — "N untested symbols" sweeps for each subsystem). This was a one-time scan-and-file batch, genuinely drained. Ongoing test-coverage work (guardrails, harness) now lives in Developer Experience #64 and API Surface & Test Harness #70. Correctly closed; not a duplicate. |
| 83 | 0 | 23 | AI Infrastructure | Fully closed, 23 issues (EPIC #2056 + its 22 children: MLX/local-model reuse/batching/cloud-leak-gating/embeddings-pin). **This is the true duplicate**: AI Backend Hardening #90 is the *direct sequel* — same theme (efficient/private/local model use), different Opus-review pass, still has 1 open issue (#2615 "Embedded local models: ship Apple Foundation Models + MLX"). Confirms brief's suspicion — #83 closed too soon relative to the live theme, but the fix is routing (not reopening #83): all new AI-infra work → #90, leave #83 closed-historical. |
| 86 | 1 | 0 | Source Archive - GHG/GHC/ACENET | **Closed milestone with 1 OPEN issue** (#1233, re-verified live: `open_issues:1, closed_issues:0, state:closed`). Confirms brief: Daniel reopened the issue but the milestone itself is still marked closed — a housekeeping bug, not a design decision. Fold into Source Archives umbrella (§3). |
| 87 | 1 | 0 | Source Archive - Sergio Notebook | Same bug: closed milestone, 1 OPEN issue (#1235, re-verified: `open_issues:1, closed_issues:0, state:closed`). Fold into Source Archives umbrella (§3). |
| 101 | 0 | 5 | Networking — OpenAPI-only (kill hand-rolled URLSession) | Fully closed, 5/5 issues done (#2410 EPIC + 4 conversion issues, all merged). Genuinely complete migration; the *guardrail* that keeps it true going forward (`#2393 Guardrail: ban raw URLSession...`) is filed under Programmatic Guardrails #92, already closed there too. Correctly closed, not a duplicate — this is enforcement-by-guardrail-going-forward exactly as the brief anticipated. |
| 108 | 0 | 6 | Docs Review | Fully closed, 6 issues, all "Daniel reviews public site/docs X" one-time review passes (site launch review). Ongoing documentation work (manual, dev docs, screenshots) lives in Documentation #67. Correctly closed as a one-time review batch, not a duplicate of #67 (different verb: review-once vs. maintain-ongoing). |

---

## 2. Closed↔open duplicate map

| Closed milestone | Verdict | Reasoning (grounded) |
|---|---|---|
| **Infrastructure #11** | (b) genuinely done/historical, themes now live elsewhere | 247 issues read; all closed feature/bugfix work from 0.0.1–0.0.3 hardening passes. No open issues anywhere still reference it as home. Leave closed. |
| **CLI #63** | (c) closed-too-soon → **fold into Developer Experience #64** | Milestone itself only ever had 2 stale-test issues; the real CLI theme (EPIC #2884 + 7 open issues) already lives in #64. No action needed on #63 itself (leave closed, 0 open) — just confirms routing: all new CLI issues → #64, never recreate a CLI milestone. |
| **Source Archives #65** | (c) closed-too-soon → **reopen, use as the umbrella** | 3 issues (#1234 Medellin, #1238 Istmina, #1231 slipbox) all closed, but these are demo/test corpora — same class as the 6 per-corpus milestones, all still "ongoing" per Daniel. Reopen #65 as the single Source Archives umbrella (§3/§4). |
| **Security #69** | (b) genuinely done/historical | 20 CVE-class issues, all fixed. New auth/security work correctly opened new milestones (#110 Connection & Startup, #111 Multi-user & Shared) rather than reusing #69 — that's the right call since #69 was a *hardening sprint* not an *ongoing surface*. Leave closed, do not fold #110/#111 into it. |
| **Native SwiftUI Controls #78** | (b) genuinely done/historical (1-issue guardrail milestone) | Only ever held 1 guardrail issue. Not a real duplicate of #79/#93/#94 — those are the correct ongoing homes for native-control UI work. Leave closed. |
| **Test Coverage #82** | (b) genuinely done/historical | One-time auto-filed scan batch (26 "N untested symbols" issues), fully drained by design — a scan-and-file exercise, not a recurring milestone. Leave closed; ongoing coverage/guardrail work → Developer Experience #64. |
| **AI Infrastructure #83** | (c) closed-too-soon, but the correct fix is routing not reopening → **all new/renewed AI-infra work goes to AI Backend Hardening #90** | 23/23 issues closed but is the direct predecessor of #90 (which is itself still 1-open/24-closed and clearly the live continuation of the same theme, including EPIC #2056's remaining local-model work via #2615). Confirms brief's suspicion of a duplicate pair. Leave #83 closed-historical (don't reopen — its issues are done); route new filings to #90. |
| **Source Archive - GHG/GHC/ACENET #86** | (c) closed-too-soon (housekeeping bug) → **reopen, then fold into Source Archives umbrella** | Milestone `state:closed` but carries 1 open issue (#1233) — inconsistent state. Reopen briefly to move #1233 out, then re-close empty (§6). |
| **Source Archive - Sergio Notebook #87** | (c) closed-too-soon (housekeeping bug) → **reopen, then fold into Source Archives umbrella** | Same bug: `state:closed` with 1 open issue (#1235). Reopen briefly to move #1235 out, then re-close empty (§6). |
| **Networking — OpenAPI-only #101** | (b) genuinely done/historical | 5/5 issues closed — full URLSession→OpenAPI migration done. Guardrail #2393 (already closed, lives under Programmatic Guardrails #92) is the going-forward enforcement, exactly matching the brief's framing. Leave closed. |
| **Docs Review #108** | (b) genuinely done/historical | 6/6 one-time "Daniel reviews X" issues, all closed — a review pass, not an ongoing milestone. Leave closed; ongoing docs work → Documentation #67. |

---

## 3. Reopen list

Concrete issues that need to move because their *milestone* was closed too soon relative to live/ongoing work. This is entirely the Source Archives cluster — no other closed milestone needs an issue moved (Infrastructure/Security/Native-Controls/Test-Coverage/Networking/Docs-Review/AI-Infra are all correctly drained-and-closed; only *routing* changes for those, covered in §5).

**Reopen `Source Archives #65`** (state:closed → open) and use it as the single umbrella. It already owns:
- #1234 "Release data: import Archivo Judicial de Medellin catalogue into Fichero" (closed — leave as closed issue, historical; Medellin has no separate open work right now)
- #1238 "Release data: one-time import of Istmina mineria transcript workflow outputs into Fichero" (closed — same, historical)
- #1231 "Release data: import slipbox from Tinderbox and filesystem into Fichero" (closed — same, historical)

Move into the reopened umbrella (`gh issue edit N --milestone "Source Archives"`):

| From milestone | Issue | Title | State | Action |
|---|---|---|---|---|
| Source Archive - ICANH #84 | #2464 | ICANH library shows no PDFs (had many) — verify data present, fix listing | OPEN | move |
| Source Archive - ICANH #84 | #2208 | Source Archive: ICANH/Andagoya importer + Spanish Script transcription QA | OPEN | move |
| Source Archive - Marshall Diaries #85 | #1798 | IIIF/Marshall transcription text is bilingual → Spanish/dup KG | OPEN | move |
| Source Archive - Marshall Diaries #85 | #1708 | EPIC: Marshall IIIF/W3C importer reliability + staged data contract | OPEN | move |
| Source Archive - Marshall Diaries #85 | #1667 | Marshall SMB staging logs missing 1928 enhanced image files during rsync | OPEN | move |
| Source Archive - Marshall Diaries #85 | #1236 | Release data: import Newton C. Marshall diary materials into Fichero | CLOSED | move (historical) |
| Source Archive - Archivos Nuestros #88 | #2209 | Source Archive: Archivos Nuestros importer + reproducible library QA | OPEN | move |
| Source Archive - Maps of the Black Pacific #89 | #1654 | Importer: Black Pacific / Colombian Pacific maps → IIIF + W3C | OPEN | move |
| Source Archive - Maps of the Black Pacific #89 | #1331 | Importer: Black folder + Maps folder metadata fusion | OPEN | move |
| Source Archive - Maps of the Black Pacific #89 | #1232 | Release data: create Fichero database for Chota Valley and Colombian Pacific maps | CLOSED | move (historical) |
| Source Archive - GHG/GHC/ACENET #86 (closed, but 1 open issue) | #1233 | Release data: import already-catalogued GHC materials (incl. ACENET) into Fichero | **OPEN** | move (Daniel confirmed NOT done) |
| Source Archive - Sergio Notebook #87 (closed, but 1 open issue) | #1235 | Release data: import Sergio Mosquera notebooks and catalogue spreadsheet into Fichero | **OPEN** | move (Daniel confirmed NOT done) |

After the moves, milestones #84, #85, #86, #87, #88, #89 are empty. Close #84/#85/#88/#89 (currently open, now empty). #86/#87 are already `state:closed` — leave closed, just now correctly showing 0 open issues too.

No other reopens are needed. Every other closed-too-soon *judgment call* (AI Infrastructure #83, CLI #63) is resolved by **routing new issues to the live milestone**, not by reopening the old one — since the old milestone's own issues are genuinely done, only the *theme* continues elsewhere.

---

## 4. Target taxonomy

Bands/order from the prior re-dating pass are untouched. This section only changes the **closed-milestone duplicates** and the **source-archive split**, per the brief.

### Merges

| Source milestone(s) | Canonical milestone | What happens |
|---|---|---|
| Source Archive - ICANH #84 | Source Archives #65 (reopened) | Move #2464, #2208 → #65; close #84 |
| Source Archive - Marshall Diaries #85 | Source Archives #65 (reopened) | Move #1798, #1708, #1667, #1236 → #65; close #85 |
| Source Archive - Archivos Nuestros #88 | Source Archives #65 (reopened) | Move #2209 → #65; close #88 |
| Source Archive - Maps of the Black Pacific #89 | Source Archives #65 (reopened) | Move #1654, #1331, #1232 → #65; close #89 |
| Source Archive - GHG/GHC/ACENET #86 | Source Archives #65 (reopened) | Move #1233 → #65; #86 stays closed (already closed, now correctly 0 open) |
| Source Archive - Sergio Notebook #87 | Source Archives #65 (reopened) | Move #1235 → #65; #87 stays closed (already closed, now correctly 0 open) |

No other milestone merges. Infrastructure #11, Security #69, Native SwiftUI Controls #78, Test Coverage #82, AI Infrastructure #83, Networking—OpenAPI-only #101, Docs Review #108, CLI #63 all stay closed exactly as-is — they are historical batches, not live duplicates, and their *themes* already correctly route to their modern successor milestones (§2/§5). Distinct product surfaces (Library&Reading, KG, Search, Chat, Workflows, Researcher, etc.) are untouched per instructions.

Net result: **65 milestones → 59 milestones** (6 source-archive milestones collapse into 1 reopened umbrella; 5 folded milestones — #84,#85,#86,#87,#88,#89 minus the umbrella itself = 6 folded, net -6 in the open-milestone count, +0 new milestones created).

### Milestone count after execution
- Closed, unchanged: #11, #63, #69, #78, #82, #83, #101, #108 (8)
- Closed, now correctly-empty (was 1-open bug): #86, #87 (2)
- Newly closed-empty (folded): #84, #85, #88, #89 (4)
- Reopened: #65 (1, now the Source Archives umbrella, open with 12 issues)
- All other open milestones: unchanged (53 minus #84/#85/#88/#89 which are now closed = 49, plus #65 reopened = 50)

Total surviving milestones: 50 open + 15 closed = 65 (no milestone deleted, per instructions — closed-empty ones are kept, just drained).

---

## 5. Routing rule

One line per surviving milestone — where does a *new* issue about X go. (Closed milestones are listed too, with "do not use — see canonical" where applicable, since a manager scanning the board needs to know not to reopen them.)

**Open, live milestones (route new issues here):**

- #12 Mind Palace → RealityKit/3D spatial library view work
- #13 Image Editing → crop/rotate/enhance/non-destructive image edits
- #14 Exporter → export to Word/PDF/Excel/JSON/Markdown/static-site
- #17 Search → BM25/dense retrieval/ranking
- #20 Settings & Providers → AI provider config, settings UI
- #22 Chat → first-party chat surface UI
- #52 MCP → MCP server surface for outside agents
- #53 Researcher → agentic research surface
- #54 Workflows → workflow editor (non-hardening feature work)
- #55 KG & Hermeneutics → typed entity layer, CRUD, claims
- #56 Activity & Automation → Activity Monitor + Automation surface
- #57 Importers → import tools/loaders (generic, not source-archive-specific)
- #60 Library & Reading Surface → multi-pane reading surface
- #62 Mac App Shell → macOS app chrome
- #64 Developer Experience → build/test/docs tooling for contributors, **CLI hardening (all CLI issues, per #2884)**, guardrails-for-devs, verify pipeline
- #65 Source Archives (reopened umbrella) → **every corpus/demo-dataset issue** (ICANH, Marshall, Archivos Nuestros, Maps, GHG/ACENET, Sergio, any future corpus)
- #66 Website → tubb.ca/fichero public site
- #67 Documentation → end-user manual, developer docs, screenshots, ongoing doc maintenance
- #68 Bibliography & Citations → references/citations management
- #70 API Surface & Test Harness → engine reachability/testability/sync-verification
- #71 Window Chrome & Toolbars → toolbar de-duplication
- #73 Curation → multi-select disable/group/delete/merge/unmerge/reclassify
- #74 Remote & Self-Hosting → remote engine operation
- #75 Sharing & Collaboration → share button/link, multi-writer presence
- #76 Notifications & Watchlist → system notifications, watchlists
- #77 Observable Data Layer → @Observable store architecture
- #79 Mac Polish → fonts/SF Symbols/no-emoji/status-redesign/Liquid-Glass polish
- #81 Multiplatform — iOS/iPadOS/Mac → adaptive Apple UI shell
- #90 AI Backend Hardening → **all AI-infra/model-use hardening (successor to closed #83)** — local MLX, embeddings, cloud-leak gating, provider reliability
- #91 Workflows & Catalogue Hardening → workflow/catalogue reliability bugs (Opus-review-driven)
- #92 Programmatic Guardrails → machine-enforced design-brief guardrails (successor enforcement point for closed #101, #82, #78 themes)
- #93 UI Reform — Representations → alternative representation/view-mode work
- #94 UI Reform — Inspector & Annotation → modular/floating inspector, annotation tools
- #95 visionOS → Vision Pro port
- #96 Device Pairing & Discovery → QR/code pairing, engine discovery
- #97 Archive Capture — Mobile & Camera Intake → capture intake (post-pairing)
- #98 Archive Capture — Automation & Provenance → capture-batch workflow automation
- #99 Watched-Entity Research Agents → entity/name/place watchlist agents
- #100 Clip Service — Web & Document Capture → web/URL/document clipping
- #102 Chat & Agent → in-app agentic control surface
- #103 Repo Hygiene & Structure → repo cleanup/restructure/onboarding
- #104 SwiftUI App Structure & Naming → fichero/fichero/ reorg
- #105 iOS/iPad Embedding & Multi-Library → embedded engine + multi-library architecture
- #106 Release & Distribution → signing, Sparkle, dated releases
- #107 Node Model & Endpoint Unification → node-model collapse of subsystem sprawl
- #109 Dev & Build Harness → reproducible debug/test/release/testflight build+launch
- #110 Connection & Startup Bulletproofing → connection path hardening (successor to closed #69's connection-facing half)
- #111 Multi-user & Shared Libraries → multi-user sharing UX, per-library access (successor to closed #69's multi-user half)
- #112 iOS/iPad/Mac UX → cross-platform interaction model
- #113 Import & Index Modes → copy/move/link/index import semantics
- #114 tvOS → Apple TV port

**Closed milestones (do NOT file into these — route to the canonical listed):**

- #11 Infrastructure — CLOSED, historical. Route new infra issues to the specific successor: security→(new work only, no active security milestone exists — flag for Daniel if a new security issue appears, likely needs #110/#111), workflow/KG bugs→#91/#55, CLI→#64, tests→#64/#70.
- #63 CLI — CLOSED, historical. Route ALL new CLI issues → **#64 Developer Experience**.
- #69 Security — CLOSED, historical. Route new connection/auth issues → **#110 Connection & Startup Bulletproofing**; new multi-user/sharing-permission issues → **#111 Multi-user & Shared Libraries**.
- #78 Native SwiftUI Controls — CLOSED, historical. Route new native-control issues → **#79 Mac Polish** (fonts/controls polish) or **#93/#94 UI Reform** (structural representation/inspector work using native controls).
- #82 Test Coverage — CLOSED, historical. Route new test-coverage-gap issues → **#64 Developer Experience**.
- #83 AI Infrastructure — CLOSED, historical. Route ALL new AI-infra/model-use issues → **#90 AI Backend Hardening**.
- #86 Source Archive - GHG/GHC/ACENET — CLOSED, now empty. Route new GHG/ACENET corpus issues → **#65 Source Archives**.
- #87 Source Archive - Sergio Notebook — CLOSED, now empty. Route new Sergio corpus issues → **#65 Source Archives**.
- #84 Source Archive - ICANH — CLOSED (newly folded), empty. Route → **#65 Source Archives**.
- #85 Source Archive - Marshall Diaries — CLOSED (newly folded), empty. Route → **#65 Source Archives**.
- #88 Source Archive - Archivos Nuestros — CLOSED (newly folded), empty. Route → **#65 Source Archives**.
- #89 Source Archive - Maps of the Black Pacific — CLOSED (newly folded), empty. Route → **#65 Source Archives**.
- #101 Networking — OpenAPI-only — CLOSED, historical. Route new URLSession/OpenAPI-transport violations → **#92 Programmatic Guardrails** (the guardrail is the enforcement mechanism now, per #2393).
- #108 Docs Review — CLOSED, historical. Route new "review this doc" requests → **#67 Documentation**.

---

## 6. Implementation command list

Ordered: (a) reopen merge targets, (b) move issues, (c) close now-empty source milestones. **No `gh issue delete` or milestone DELETE anywhere** — closed-empty milestones are left closed, never removed.

```bash
# --- (a) Reopen the merge target ---
gh api -X PATCH repos/dtubb/fichero/milestones/65 -f state=open   # Source Archives → umbrella, reopened

# --- (b) Move issues into the reopened umbrella ---
# From Source Archive - ICANH #84
gh issue edit 2464 --milestone "Source Archives"
gh issue edit 2208 --milestone "Source Archives"

# From Source Archive - Marshall Diaries #85
gh issue edit 1798 --milestone "Source Archives"
gh issue edit 1708 --milestone "Source Archives"
gh issue edit 1667 --milestone "Source Archives"
gh issue edit 1236 --milestone "Source Archives"   # closed issue, historical — still move for a single home

# From Source Archive - Archivos Nuestros #88
gh issue edit 2209 --milestone "Source Archives"

# From Source Archive - Maps of the Black Pacific #89
gh issue edit 1654 --milestone "Source Archives"
gh issue edit 1331 --milestone "Source Archives"
gh issue edit 1232 --milestone "Source Archives"   # closed issue, historical

# From Source Archive - GHG/GHC/ACENET #86 (milestone itself stays closed; issue is open)
gh issue edit 1233 --milestone "Source Archives"

# From Source Archive - Sergio Notebook #87 (milestone itself stays closed; issue is open)
gh issue edit 1235 --milestone "Source Archives"

# --- (c) Close now-empty source-archive milestones (#86 and #87 are already closed — no action needed) ---
gh api -X PATCH repos/dtubb/fichero/milestones/84 -f state=closed   # Source Archive - ICANH, now empty
gh api -X PATCH repos/dtubb/fichero/milestones/85 -f state=closed   # Source Archive - Marshall Diaries, now empty
gh api -X PATCH repos/dtubb/fichero/milestones/88 -f state=closed   # Source Archive - Archivos Nuestros, now empty
gh api -X PATCH repos/dtubb/fichero/milestones/89 -f state=closed   # Source Archive - Maps of the Black Pacific, now empty

# --- Verification ---
gh api repos/dtubb/fichero/milestones/65 -q '{number,state,title,open_issues,closed_issues}'
for n in 84 85 86 87 88 89; do gh api repos/dtubb/fichero/milestones/$n -q '{number,state,title,open_issues,closed_issues}'; done
```

No other milestone needs a state change or issue move: every other closed↔open pair (Infra/CLI/Security/Native-Controls/Test-Coverage/AI-Infra/Networking/Docs-Review vs. their open successors) is resolved purely by the **routing rule (§5)** going forward — the closed milestones' own issues are genuinely done and should not be reopened or have issues moved out of them.

---

## Decisions needing Daniel's confirmation before execution

1. **Reopening #65 "Source Archives" as the umbrella** rather than creating a fresh milestone — recommended to avoid a 66th milestone, but it does mean the umbrella carries 3 already-closed historical issues (#1234, #1238, #1231) alongside new open corpus work. Confirm this is fine, or if a clean umbrella (all-open) is preferred, we'd create #115 instead and leave #65 closed.
2. **#86/#87 stay closed-but-emptied** rather than reopened — since Daniel already re-opened the underlying issues (#1233, #1235) as separate action, the milestones themselves never got flipped back. Confirm it's fine to leave the *milestone* container closed forever once its issue moves to #65 (recommended, since #65 is now the umbrella), vs. wanting #86/#87 reopened too for historical visibility.
3. **AI Infrastructure #83 vs AI Backend Hardening #90**: recommending "leave #83 closed, route everything new to #90" rather than reopening #83 or merging #90 into #83. Confirm this direction (#90 as canonical) rather than the reverse.
4. **CLI #63 stays essentially inert** (2 closed issues, will likely never gain new ones) rather than being explicitly deprecated/relabeled — confirm this is acceptable or if Daniel wants its title changed to "CLI (deprecated — see Developer Experience #64)" for board clarity.
5. **Infrastructure #11's sprawl**: I did not propose reopening or splitting it (247 closed issues, correctly historical), but flag that if any *new* security-adjacent issue doesn't cleanly fit #110 or #111, there is currently no "general security" open milestone — confirm whether that gap should be filled or handled case-by-case.
