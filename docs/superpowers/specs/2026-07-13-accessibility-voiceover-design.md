# Accessibility & VoiceOver — audit + design (#3690)

Date: 2026-07-13 · Milestone: Accessibility & VoiceOver · Author: Claude (Opus 4.8)

Audit of the shipped SwiftUI app (586 Swift files, `fichero/fichero`) plus the
Reader's WebKit HTML, and the accessibility model the rest of the milestone
(#3691–#3695) should build to. **No source edits** — this is the plan.

Daniel's note on the issue — *"I'm not sure what else accessibility has"* — is
answered in §6: the audit surfaced four things beyond VoiceOver/Dynamic Type/
contrast/reduce-motion that are worth their own work.

---

## 1. Where we actually stand

Counted across `Views/` (grep, so ±, but the shape is right):

| API | Uses |
|---|---|
| `.accessibilityLabel` | 125 |
| `.accessibilityIdentifier` (UI-test hooks, not a11y) | 37 |
| `.accessibilityHidden` | 7 |
| `.accessibilityHint` | 5 |
| `.accessibilityElement` | 3 |
| `.accessibilityAddTraits` | 2 |
| `.accessibilityValue` | 1 |
| `.accessibilityRotor` / `.accessibilityAction` | 1 |
| `dynamicTypeSize` (any use) | **0** |

56 of 586 files touch accessibility at all. So: labels are the only widely-used
API; traits, values, hints, grouping and rotors are effectively absent.

### Coverage is not uniform — it clusters

Icons (`Image(systemName:)`) vs `.accessibilityLabel`, by surface:

| Surface | Icons | a11y labels | Read |
|---|---:|---:|---|
| Toolbars | 37 | 33 | **covered** |
| Sidebar | 19 | 13 | mostly covered |
| Space | 5 | 5 | covered |
| Library | 161 | 61 | partial — the big one |
| Activity / Chat / Notes / Settings | 29/20/7/10 | 3/2/2/3 | thin |
| **Workflow** | 75 | 1 | **bare** |
| **KnowledgeGraph** | 43 | 0 | **bare** |
| **AIProviders / MCPServers / Automation / Actions** | 26/16/14/10 | 0 | **bare** |
| Menu | 14 | 0 | bare (124 Buttons) |
| Research / Search / Sheets / Onboarding / Spatial | 9/6/9/3/6 | 0 | bare |

This is the milestone's real shape: **#3691 is not a uniform sweep.** Toolbars and
Sidebar were done properly and are the model to copy; Workflow, KnowledgeGraph, and
the provider/server/automation settings surfaces have never been touched.

A caveat on those numbers: many icons sit inside `Label("Text", systemImage:)`
(531 uses), which VoiceOver already reads from the title — those are fine and need
**no** label. The gap is icon-*only* `Button { Image(systemName:) }`, which reads as
the raw SF Symbol name or as nothing. The per-surface sweep has to distinguish the
two rather than blanket-adding labels (a label on a `Label` is redundant noise).

### Custom-drawn views: invisible to VoiceOver

These render pixels with zero accessibility surface. VoiceOver reaches *nothing*
inside them:

- `Views/Spatial/*` — SpatialView, Spatial2DCanvasItems/Gestures, SpatialNodeThumbnail (0)
- `Views/Preview/DocumentCanvas.swift` (0)
- `Views/Preview/PDFViewer/PDFPageView.swift`, `PDFLoupeOverlay.swift` (0)
- `Views/Reader/Page/AnnotatableTextView.swift` (0) — the annotation surface
- `Views/Preview/ImageViewer/*` — partial: `ImageViewerComponents` (14) and
  `MagnifierPanel` (8) are labelled; `NavigatorMiniMap`, `TrackingImageView`,
  `CheckerboardPattern`, `ScrollWheelZoom` are not.

`Image(nsImage:)` / `AsyncImage` (document thumbnails) appear 6× — each needs a
label naming the *document*, not "image".

### What is already right — don't regress it

- **Reduce Motion is genuinely respected** in 4 places, and correctly: it degrades
  the transition to `.opacity` rather than disabling it
  (`ContentView+ViewBuilders.swift:519`, `ImmersiveReaderView.swift:354`,
  `ContentViewHelperViews.swift:99`, `SkeletonPlaceholder.swift:26`). This is the
  pattern #3695 should extend, not replace.
- **Semantic fonts** are the house rule and largely hold; the Reader/Editor
  typography work (#3681/#3682) scales the *semantic base*, so it already composes
  with Dynamic Type instead of fighting it.
- **The Reader HTML sets `lang="en"`** and both generated SVGs carry
  `role="img"` + a real `aria-label`
  (`fichero-engine/src/fichero/api/templates/document_view.html:897,1127`).

---

## 2. The accessibility model (conventions for #3691)

One convention, applied per surface. Written as rules a worker can follow without
re-deciding:

1. **Label = what it does, not what it looks like.** `"Delete annotation"`, never
   `"trash icon"` and never the SF Symbol name.
2. **`Label("Text", systemImage:)` needs no `.accessibilityLabel`.** Add one only
   to icon-*only* controls. Adding a label to an already-titled control is noise.
3. **Traits carry state, not prose.** Selected/expanded/disabled go through
   `.accessibilityAddTraits(.isSelected)` etc. Never bake "selected" into a label
   string — VoiceOver already announces the trait, so it would double-speak.
4. **`.accessibilityValue` for anything with a current setting** — the font-size
   steppers, zoom level, page number. Today: 1 use in the whole app.
5. **Hints are the exception, not the rule** (5 uses today, which is about right).
   A hint is for a non-obvious *gesture*, not a description of the control.
6. **Decorative art is hidden**: `.accessibilityHidden(true)` on chrome, rules,
   checkerboards, glyphs that repeat an adjacent title. Hiding noise is as much of
   the work as adding labels.
7. **Group composite rows into one element.** A document row that reads as five
   separate elements (thumbnail, title, date, badge, chevron) should be one
   `.accessibilityElement(children: .combine)` with a label and traits. This is the
   single biggest VoiceOver quality win in the Library, and needs 3 uses → many.
8. **Colour is never the only cue** — 40 `Circle()` status dots. Each needs a label
   ("Failed", "Running") and, for `.differentiateWithoutColor`, a shape/glyph
   difference too.

### Custom views: represent, don't re-implement

For Spatial, DocumentCanvas, PDFPageView, AnnotatableTextView the answer is
**`.accessibilityRepresentation`** (or `accessibilityChildren`) — expose the model
that the pixels stand for (a node, an annotation, a page) as real SwiftUI elements,
rather than hand-rolling a parallel accessibility tree. The data is already in the
stores; the drawing layer is the only thing that lost it.

---

## 3. Reader VoiceOver + rotor (#3692 / #3693)

The Reader is WebKit, so this is **not** a SwiftUI accessibility problem — and that
is the load-bearing finding for these two issues.

- Paragraph-by-paragraph navigation should come from the **HTML structure**: real
  `<p>` elements and heading levels in
  `fichero-engine/src/fichero/api/templates/document_view.html` (and the Swift-built
  HTML in `Views/Reader/Knowledge/DocumentKGWebPane.swift:62`). VoiceOver's *existing* web
  rotor then navigates by paragraph/heading for free. A SwiftUI
  `.accessibilityRotor` cannot see into a WKWebView and is the wrong tool here.
- The template today has `lang` and labelled SVGs but **no heading structure or
  landmark roles** in the prose body — that is the actual work of #3692.
- **#3693 (highlight the VoiceOver-read paragraph → Notes)** needs a paragraph to
  have a stable identity to attach the note to. Each `<p>` needs a stable id
  emitted by the engine template, and the existing annotation/notes path keys off
  it. **#3692 must land before #3693**; #3693 is otherwise designing on sand.

Reader theme/contrast (#3695) also lands in the CSS: the Reader already var-drives
its colours from the app (`systemThemeCSS()` / `themeInjectionScript()`), so
`prefers-contrast` / `prefers-reduced-motion` belong in **that** existing injection
path — no new mechanism.

---

## 4. Dynamic Type (#3694)

Zero `dynamicTypeSize` uses. The good news is the semantic-font rule means most
text already scales; the work is the exceptions:

- **71 hardcoded `.system(size:)`** remain — concentrated in
  KnowledgeGraph/OntologyBrowser (7 files), Workflow (5), Library (5), Sidebar (4).
  Per the standing rule, **not all of these are wrong** — display/weighted/serif/
  mono and deliberate conditional sizing are intentional. Each must be judged, not
  bulldozed. The wrong ones are body-prose-at-a-fixed-size.
- **Layouts must survive `.accessibility5`** — fixed-height rows, `.frame(height:)`
  on text containers, and single-line truncation are where large type breaks. This
  is a per-surface *layout* audit, not a font sweep, and it is the bulk of #3694.
- Reader/Editor scale (#3681/#3682) **multiplies** the semantic base, so the two
  compose. Test the pair together at 2.0× scale + `.accessibility5`.

---

## 5. Issue reconciliation

| Issue | Verdict |
|---|---|
| **#3691** labels/traits/hints | **Split.** Too big as one issue and it collides with every lane. Slice per surface, matching the coverage table: (a) Workflow, (b) KnowledgeGraph, (c) AIProviders + MCPServers + Automation + Actions, (d) Library rows/grouping, (e) Chat/Activity/Notes/Search/Sheets, (f) custom views via `accessibilityRepresentation`. Toolbars/Sidebar/Space need **no** work. |
| **#3692** Reader rotor | Re-scope: this is **engine-template HTML structure** (`<p>`/headings/stable ids), not SwiftUI `.accessibilityRotor`. Backend lane, not Swift. |
| **#3693** highlight read paragraph → Notes | **Blocked on #3692** (needs stable paragraph ids). Sequence it after. |
| **#3694** Dynamic Type | Re-scope from "adopt Dynamic Type" to "**survive** Dynamic Type": audit the 71 `.system(size:)` case-by-case (many are intentional) + fix layouts that break at `.accessibility5`. |
| **#3695** Reduce Motion + Contrast | Reduce Motion is **already done correctly in 4 places** — the work is (a) extend the same pattern to the remaining ~59 animation sites, (b) `.differentiateWithoutColor` for the 40 colour-only status dots, (c) `prefers-contrast` in the Reader CSS. |
| **new** | Colour-contrast pass on custom-drawn surfaces (Spatial, Canvas) — see §6. |
| **new** | Keyboard-only navigation + focus order — see §6. |

Lane note: #3691's Library and Inspector slices **overlap the live Drag & Drop lane**
(#3704/#3705). Those two slices must wait for that lane to land; the Workflow /
KnowledgeGraph / providers slices are disjoint and can start immediately.

---

## 6. "What else does accessibility have" — beyond the four

The audit surfaced four gaps that none of #3691–#3695 covers:

1. **Keyboard-only navigation and focus order.** Nothing in the app declares focus
   order; a keyboard-only user cannot necessarily reach every control, and the
   custom-drawn surfaces are unreachable by definition. This is a real accessibility
   requirement, not a nicety. → **Already covered by #3686** (Keyboard Navigation
   milestone); no duplicate filed. The audit's addition, noted on that issue: the
   custom-drawn surfaces are unreachable *by construction*, not merely mis-ordered,
   so #3686 and #3691's `accessibilityRepresentation` work must be sequenced
   together.
2. **`.accessibilityIdentifier` is being used for UI tests (37×), not accessibility.**
   That is legitimate, but it means identifier coverage must not be mistaken for
   accessibility coverage — they are different axes and the numbers look similar.
3. **VoiceOver announcements for async state.** Import, indexing and workflow runs
   change state with no announcement; a blind user gets silence while a progress bar
   moves. Needs `AccessibilityNotification.Announcement` at the transition points
   (started / completed / **failed** — a silent failure is the worst case), hooked
   where the state already lands rather than sprinkled through views.
   → **Filed as #3724** on this milestone.
4. **Reduce Transparency / Increase Contrast on the app chrome** (materials,
   `.ultraThinMaterial` backgrounds) — unchecked, and separate from the Reader CSS.
   → Folds into **#3695**.

Disposition (Daniel, 2026-07-13): 1 → #3686 (no duplicate), 3 → #3724, 4 → #3695.
2 stays a documentation note: `.accessibilityIdentifier` coverage is a UI-test axis
and must not be read as accessibility coverage.

---

## 7. Verification

VoiceOver correctness is not unit-testable, and pretending otherwise produces
green tests that mean nothing. Split it:

- **Testable in `fichero-tests`** — the *logic*: that a row's composed
  accessibility label is built from the right model fields, that a status maps to
  the right label string, that the reduce-motion branch returns `.opacity`. These
  are pure functions and should be extracted so they can be asserted.
- **Not testable — must be driven by hand** on the built app: actual VoiceOver
  reading order, rotor navigation, layout at `.accessibility5`. Each implementation
  issue ships with the manual VoiceOver check named in its acceptance criteria, and
  the Accessibility Inspector's audit is run per surface.

Do not claim a surface is accessible because a label exists in the source. The bar
is that VoiceOver reads it correctly, in order.
