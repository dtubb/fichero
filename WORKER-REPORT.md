# Worker Report — Programmatic Guardrails milestone (lane/guardrails)

Author: Claude (commits authored as Claude, co-authored Daniel Tubb). **Not pushed** — manager merges + runs verify_all.

Branch base: `55036ddf` (main merge). 6 commits added, one per issue.

---

## Guardrails added (each `scripts/check_*.py`, auto-discovered by verify_all.sh's `scripts/check_*.py` loop — no manual wiring needed)

| # | Issue | Script | Checks | Seeded violations | Exit 0? |
|---|-------|--------|--------|-------------------|---------|
| 1 | #2285 | `check_accessibility.py` | Icon-only `Button` (Image-only, no text Label/Text) missing `.accessibilityLabel(...)` → invisible to VoiceOver | **149** in `check_accessibility_known_violations.json` | ✓ |
| 2 | #2660 | `check_generated_wrapper_drift.py` | Every `Components.Schemas.<Name>` referenced in `Services/*Generated.swift` resolves to a current OpenAPI schema (reproduces swift-openapi `idiomatic` naming) | **0** (clean — wrappers compile today) | ✓ |
| 3 | #2286 | `check_applescript_coverage.py` | Bidirectional `Fichero.sdef` ↔ Swift: every advertised `<cocoa class="Fichero*">` has a Swift class, and every `NSScriptCommand` subclass is advertised | **0** (14 classes, 10 commands, lock-step) | ✓ |
| 4 | #2287 | `check_localization.py` | Bans `Text(verbatim: "<prose>")` — the one SwiftUI escape hatch from `LocalizedStringKey` localization | **0** (no verbatim prose today) | ✓ |
| 5 | #2270 | `check_import_render_completeness.py` | Every engine `DocType`/`FileType` (importable) is handled by the Swift decoder switch (`convertFromGenerated*` in DocumentServiceGenerated.swift) → renders in ≥1 representation | **0** (clean — decoder handles all; docx folds to word) | ✓ |

Each ships a `test_check_*.py` in `fichero-engine/tests/unit/` (26 tests total, all pass). `--list` and `--help` on every script.

### Detail per check

**#2285 Accessibility** — modeled on the shipped `check_tooltips.py`. Scans `fichero/fichero/**/*.swift`, strips comments + `#Preview`. Flags icon-only Buttons lacking `.accessibilityLabel`. Text-labeled buttons and `Label("text", systemImage:)` are auto-announced and skipped. 149 current violations seeded (verified true positives, e.g. ChatInputView send button, ActionPickerView clear button). Regenerate baseline with `--update` after legitimately adding controls.

**#2660 Generated wrapper drift** — closes the exact gap that broke the Release build 2026-06-26. Parses `openapi.json`, computes the `namingStrategy: idiomatic` Swift name for all 762 schemas, asserts every wrapper reference resolves. The idiomatic transform is verified against the regression case (`fichero__knowledge__knowledge_models__EntityType → FicheroKnowledgeKnowledgeModelsEntityType`) and covers all 119 current references with zero seeded violations — so it catches drift at CI, not at Release build.

**#2286 AppleScript** — `<cocoa class>` is the contract between the .sdef dictionary and the Swift `NSScriptCommand`/`NSObject` classes. Either direction breaking is a silent runtime failure. Clean baseline.

**#2287 Localization** — see "Flagged for Daniel" below for the scope decision. Ships the zero-friction slice (ban the verbatim escape hatch); broad enforcement deferred.

**#2270 Import/render** — checks the canonical decoder (`convertFromGenerated{DocType,FileType}` in `DocumentServiceGenerated.swift`), the one point where an imported document's engine type is mapped to a local renderable type. Asserts every engine `DocType`/`FileType` is handled by that switch. Baseline clean: docx is intentionally folded onto `word` (`case .docx: return .word // docx is a Word variant`), so it renders — not a gap. (My initial version naïvely compared raw enum case-sets and false-flagged docx; corrected to read the decoder, the real classification point — see follow-up commit.) Fails when a NEW engine type lands without a decoder mapping.

---

## Other milestone issues

**#2461 — SwiftLint cleanup** (`style:` commit). Was ~112, already down to **41** when I started; cleared the **safe** ones → **30** remaining.
- Fixed (behaviour-preserving): 4 `trailing_newline`, 2 `sorted_imports`, 1 `implicit_optional_initialization` (the `@State private pinnedDocumentId`, which is not in any memberwise init).
- **Did NOT** remove `= nil` from `documentTitle`/`onClose`/`externalActiveTab`/`onTabSelected` — these are **load-bearing memberwise-init defaults**; 3 `PDFPageWithToolbar` call sites and the `KnowledgeSurface` call site omit those args, so removing `= nil` changes the synthesized initializer and **breaks the build**. (SwiftLint `--fix` would have broken it — this is a false positive of the custom `implicit_optional_initialization` rule on memberwise-init Views.) Kept `= nil` + inline `swiftlint:disable:this`.
- **Deferred** (need a full Xcode build to verify safely — I can't run `xcodebuild` on the active desktop per house rule, and CLI build locks against open Xcode): 12 `file_length`, 8 `type_body_length`, 7 `function_body_length`, 2 `cyclomatic_complexity`, 1 `todo`. These are structural splits and the `LibraryWindow.body` type-check-timeout hazard makes blind splits risky. Recommend a build-capable lane.

**#2269 — models → shared folder.** Already done: `scripts/check_model_download_location.py` exists and passes. No action.

**#2393 — ban raw URLSession.** Already done: `scripts/check_swift_hand_rolled_urls.py` + `check_swift_transport.py` exist and pass. No action.

**#2271 — EPIC: guardrail suite.** Left **open** per instructions. Did concrete child slices (#2285, #2286, #2287, #2270, #2660).

---

## Flagged for Daniel

1. **#2270 docx — RESOLVED, not a bug.** First pass flagged `FileType.docx` (engine) as having no Swift enum case. On inspection the decoder `convertFromGeneratedFileType` already folds it: `case .docx: return .word // docx is a Word variant`. So docx renders (as word). Rewrote the guardrail to check the decoder switch instead of the raw enum case-set; baseline is now genuinely clean (0 seeded), no design decision needed. No remaining action.

2. **#2287 Localization — broad enforcement deferred (intentionally not built).** The app has **no localization infra** (0 `String(localized:)`, no string catalog; #1396 not landed). In SwiftUI, `Text`/`Button`/`Label`/interpolated `Text` already localize via `LocalizedStringKey` — they are *not* bypasses. A ratchet over the ~1650 literals would force `String(localized:)` into infrastructure that doesn't exist, blocking all UI work for no benefit. So I shipped only the genuine, zero-friction slice (ban `Text(verbatim:)` prose). Enforcing `String(localized:)` for **non-View** user-facing strings (alerts/errors built in stores/services) should land **with** #1396's catalog.

3. **#2281 — every action reachable from UI+chat+App Intents+MCP — design-blocked, not built.** Analysis:
   - **chat**: auto-generated from the action registry (`actions/chat_tools.py::action_tools` iterates `reg.all()`) → 1:1 by construction, can't drift. Also the live `/api/chat` is still single-shot (no agentic tool loop yet), so chat tools aren't wired in. No useful guardrail here.
   - **App Intents** (`Intents/FicheroActionIntents.swift`) and **MCP** (`mcp_*.py`) are **curated subsets** (~5 intents vs ~109 registry actions) — by design, not everything should be a Siri shortcut / MCP tool.
   - A 4-surface matrix therefore needs a **per-action surface policy** (which actions belong on which surface) before a ratchet means anything. Seeding ~100 arbitrary allowlist entries would be inventing that policy, not enforcing it. **Needs Daniel's design decision** (it's `[design]`-flagged in #2271). Did not ship an arbitrary guardrail.

---

## Pre-existing red guardrails (NOT introduced by this branch)

⚠️ **The base commit `55036ddf` already fails 17 guardrails** (verified by running the full `scripts/check_*.py` suite in a throwaway worktree at the base — identical 17-failure set with and without my commits). My work adds **zero** new guardrail failures; all 5 new checks exit 0.

The 17 pre-existing reds: `check_action_surface_matrix`, `check_appkit_imports`, `check_canonical_renderers`, `check_comment_hygiene`, `check_dead_files`, `check_endpoint_coverage_matrix`, `check_endpoint_usage`, `check_feature_flags`, `check_folder_organization`, `check_native_controls`, `check_observer_pattern`, `check_openapi_shadow_types`, `check_python_comment_hygiene`, `check_service_consistency`, `check_test_assertions`, `check_undo_coverage`, `check_view_endpoint_access`.

When verify_all runs on this branch these will show red — they are pre-existing and out of scope for this milestone. Worth a separate triage lane.

---

## Verification done
- All 5 new `check_*.py` exit 0.
- All 26 new unit tests pass (`fichero-engine/tests/unit/test_check_*.py`).
- SwiftLint: 41 → 30 (safe subset only).
- Did **not** run `xcodebuild`/full Swift build (house rule + Xcode lock). The SwiftLint `= nil` analysis was done by reading every call site, not by building.
- Did **not** push.
