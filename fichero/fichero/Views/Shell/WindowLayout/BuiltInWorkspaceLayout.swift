import Foundation

// MARK: - Built-in workspace COMPOSITIONS (v2, spec §"v2 workspace design", 2026-09-15)

/// The six default workspaces as DATA — each a `PaneList` (kind + per-pane config + nesting), so
/// adding or editing a default is a data change and a saved workspace is the same shape ("easy to
/// set up in a backend", CD 2026-09-15). Pure; no SwiftUI.
///
/// Conventions grounded in the surface inventory:
///   - the sidebar (with chat beneath) is NOT a centre pane;
///   - the inspector always docks on the RIGHT, full height;
///   - claims / entities / related are the LIBRARY pane browsing different content
///     (`PaneConfig.libraryContentKind`), not separate kinds;
///   - the word-box overlay is the PREVIEW pane with `previewWordBoxes` on.
///
/// Names describe what each is for (CD: not app-metaphors). The declaration order is the default
/// ⌘⌥1–6 slot order; ⌘⌥7–9 are left for user workspaces (the slot→workspace map, CD-approved).
enum BuiltInWorkspaceLayout: String, CaseIterable, Identifiable, Sendable {
    case read           // ⌘⌥1  [ library·table / reader ] · preview
    case browse         // ⌘⌥2  library·icons · preview · reader
    case transcribe     // ⌘⌥3  [ preview | reader ] over library·icons
    case transcribeTall // ⌘⌥4  [ preview | word-boxes | editor ] over library·icons (three-long)
    case compare        // ⌘⌥5  [ page A | page B | reader ] over library·icons

    var id: String { rawValue }

    var title: String {
        switch self {
        case .read: "Read"
        case .browse: "Browse"
        case .transcribe: "Transcribe"
        case .transcribeTall: "Transcribe · Tall"
        case .compare: "Compare"
        }
    }

    var systemImage: String {
        switch self {
        case .read: "text.book.closed"
        case .browse: "sidebar.squares.left"
        case .transcribe: "text.viewfinder"
        case .transcribeTall: "rectangle.split.3x1"
        case .compare: "rectangle.split.2x1"
        }
    }

    /// One-line description of the arrangement (for the Manager and menus).
    var summary: String {
        switch self {
        case .read: "The table over a reader, the page beside."
        case .browse: "Icons, then the page, then the reader."
        case .transcribe: "The page and the editor over a strip of pages."
        case .transcribeTall: "The page, its word-boxes and the editor, over a strip of pages."
        case .compare: "Two witnesses side by side with the reader, over a strip of pages."
        }
    }

    /// The default ⌘⌥N slot (1-based declaration position) — the built-in half of the
    /// slot→workspace map. ⌘⌥7–9 (beyond the six) are user-assignable.
    var defaultSlot: Int { (Self.allCases.firstIndex(of: self) ?? 0) + 1 }

    /// The composition. Every node uses `.stableLeaf`/`.stableSplit`, NOT the plain `.leaf`/
    /// `.split` (SF6 review finding, fixed): the plain factories mint a fresh random `UUID()` on
    /// EVERY access, so re-deriving the same built-in — navigating Read → Browse → Read, or a
    /// relaunch re-seeding `activePaneList` from `WorkspaceLayoutDefaults.rememberedPaneList()`
    /// against `BuiltInWorkspaceLayout.read.panes` — silently lost every dragged divider and
    /// orphaned two `@SceneStorage` keys per apply, because `WorkspaceSplitStack`/`PaneSpec` key
    /// their per-instance storage off a leaf's id. Each `named:` string is unique within its own
    /// `case` (prefixed with `rawValue`, so it's also unique ACROSS built-ins) and never changes.
    var panes: PaneList {
        switch self {
        // CD 2026-09-16 — the workspace set redesigned from the CD's Mail-referenced sketch. NOTE:
        // per-pane `libraryLayout` (table vs icons) is not yet read by the renderer (it uses the
        // window's global layout); wiring that is the next step so these actually look different.
        case .read:
            // Default (Mail-style): table at top, reader below, preview to the right.
            // #4688 (CD 2026-09-17, "think through % for the various default workspaces"): the
            // table needs less height than the reader it summarizes — 40:60 gives the reader most
            // of the column while the table still shows several rows. The reader has no fraction
            // of its own; it's the LAST child of this split so it just flexes into the remaining
            // 60% (WorkspaceSplitStack's "last child flexes" rule) — one number to tune, not two
            // that could drift apart.
            return PaneList([
                .stableSplit(.vertical, named: "\(rawValue).topSplit", [
                    .stableLeaf(.library, named: "\(rawValue).library",
                                config: PaneConfig(libraryLayout: "table", paneFraction: 0.4)),
                    .stableLeaf(.reading, named: "\(rawValue).reading")
                ]),
                .stableLeaf(.preview, named: "\(rawValue).preview")
            ])
        case .browse:
            // Icon view (vertical column), then preview, then reader — "like we had it".
            // #4966 (2026-09-20): the Browse ratio is 15:60:25 — the icon strip is a
            // NAVIGATION aid, not a reading surface, so it gets the smallest, fixed share;
            // preview (the source image) gets most of the row; the reader is the last child
            // and flexes to the remainder (~25%), so it can't drift out of step with the
            // stated ratio. Was 30:35:35 (#4688) — superseded, not layered on top of.
            return PaneList([
                .stableLeaf(.library, named: "\(rawValue).library",
                            config: PaneConfig(libraryLayout: "icons", paneFraction: 0.15)),
                .stableLeaf(.preview, named: "\(rawValue).preview", config: PaneConfig(paneFraction: 0.60)),
                .stableLeaf(.reading, named: "\(rawValue).reading")
            ])
        case .transcribe:
            // Icons along the bottom, preview above and reader to its right.
            // #4688: page and editor are equal-weight transcription partners — 50:50. The film
            // strip stays a HARD absolute 72pt (`paneExtent`, unchanged) — a strip of page icons
            // is a deliberate fixed-size affordance, not a fraction of the display (CD 2026-09-16).
            return PaneList([
                .stableSplit(.vertical, named: "\(rawValue).outerSplit", [
                    .stableSplit(.horizontal, named: "\(rawValue).topSplit", [
                        .stableLeaf(.preview, named: "\(rawValue).preview", config: PaneConfig(paneFraction: 0.5)),
                        .stableLeaf(.reading, named: "\(rawValue).reading")
                    ]),
                    .stableLeaf(.library, named: "\(rawValue).library",
                                config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        case .transcribeTall:
            // Three-long (CD 2026-09-16): the page, its word-box overlay, and the editor across the
            // top, over the strip of pages. The middle preview carries the OCR word boxes — the
            // detailed-transcription triptych. Two previews are instance-safe (the focused-value
            // guard flags the second secondary).
            // #4688: all three panes are equally-weighted reading surfaces here (no natural
            // "primary" the way Read's table/reader split has one) — equal thirds. Only the first
            // two carry an explicit 0.33; reading is left as a PEER (no explicit weight) and is
            // last, so it flexes to the remaining ~34% — the same answer #4849's peer-sharing
            // rule would give it explicitly (`(1 − 0.66) / 1 peer`), stated as fractions here
            // because a workspace author picking exact numbers is clearer than three peers left
            // silently equal by omission (WorkspaceSplitStack now has three resizable slots, not
            // two — #4849 — so a third explicit column would fit too, if this ever needs one).
            return PaneList([
                .stableSplit(.vertical, named: "\(rawValue).outerSplit", [
                    .stableSplit(.horizontal, named: "\(rawValue).topSplit", [
                        .stableLeaf(.preview, named: "\(rawValue).previewA", config: PaneConfig(paneFraction: 0.33)),
                        .stableLeaf(.preview, named: "\(rawValue).previewB",
                                    config: PaneConfig(previewWordBoxes: true, paneFraction: 0.33)),
                        .stableLeaf(.reading, named: "\(rawValue).reading")
                    ]),
                    .stableLeaf(.library, named: "\(rawValue).library",
                                config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        case .compare:
            // Icons along the bottom, with TWO previews and one reader above (two witnesses side by
            // side + the reader). Two previews are instance-safe (the focused-value guard flags the
            // second secondary); the ⌘⌥4 crash was the animated swap, now removed (5bd6cf61a).
            // #4688: the two witnesses being compared are the point of this workspace, so they get
            // the lion's share equally (40:40) and the reader — reference context, not the primary
            // task here — gets the last, flexing ~20%.
            return PaneList([
                .stableSplit(.vertical, named: "\(rawValue).outerSplit", [
                    .stableSplit(.horizontal, named: "\(rawValue).topSplit", [
                        .stableLeaf(.preview, named: "\(rawValue).previewA", config: PaneConfig(paneFraction: 0.4)),
                        .stableLeaf(.preview, named: "\(rawValue).previewB", config: PaneConfig(paneFraction: 0.4)),
                        .stableLeaf(.reading, named: "\(rawValue).reading")
                    ]),
                    .stableLeaf(.library, named: "\(rawValue).library",
                                config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        }
    }
}
