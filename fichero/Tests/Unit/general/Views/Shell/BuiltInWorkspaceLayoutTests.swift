@testable import Fichero
import Foundation
import Testing

/// spec: panes-workspaces §"v2 workspace design" — the FIVE default workspaces AS DATA
/// (Read, Browse, Transcribe, Transcribe·Tall, Compare; CD 2026-09-16 dropped Catalogue + Claims —
/// Claims is a library content-filter, not a layout). These pin each composition (kinds, nesting,
/// per-pane config) so a default is a data change and a saved workspace is the same `PaneList` shape.
struct BuiltInWorkspaceLayoutTests {

    /// Every leaf (kind + config) anywhere in a list, splits flattened.
    private func allLeaves(_ list: PaneList) -> [(kind: PaneKind, config: PaneConfig)] {
        var out: [(kind: PaneKind, config: PaneConfig)] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(_, kind, _, config): out.append((kind: kind, config: config))
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        list.nodes.forEach(walk)
        return out
    }

    @Test("the five defaults map to ⌘⌥1–5 in declaration order")
    func slotsAreOneThroughFive() {
        #expect(BuiltInWorkspaceLayout.allCases.count == 5)
        for (index, layout) in BuiltInWorkspaceLayout.allCases.enumerated() {
            #expect(layout.defaultSlot == index + 1)
        }
        #expect(BuiltInWorkspaceLayout.read.defaultSlot == 1)
        #expect(BuiltInWorkspaceLayout.compare.defaultSlot == 5)
    }

    @Test("Read is the default: library over reader, beside the preview")
    func readIsLibraryOverReaderBesidePreview() {
        // CD 2026-09-16: 1 library above 1 reader (a vertical split), beside 1 preview.
        let nodes = BuiltInWorkspaceLayout.read.panes.nodes
        #expect(nodes.count == 2)
        guard case let .split(_, axis, children) = nodes.first else {
            Issue.record("Read should open with a vertical split (library over reader)"); return
        }
        #expect(axis == .vertical)
        #expect(children.map(\.kinds) == [[.library], [.reading]])
        // The preview is the second top-level column.
        #expect(nodes.last?.kinds == [.preview])
        #expect(BuiltInWorkspaceLayout.read.panes.kinds == [.library, .preview, .reading])
    }

    @Test("Browse is icon view, preview, reader — three columns (like we had it)")
    func browseIsThreeColumns() {
        let nodes = BuiltInWorkspaceLayout.browse.panes.nodes
        #expect(nodes.map(\.kinds) == [[.library], [.preview], [.reading]])
        if case let .leaf(_, _, _, config) = nodes.first {
            #expect(config.libraryLayout == "icons")
        }
    }

    @Test("Transcribe is icons along the bottom, preview + reader above")
    func transcribeIconsBottom() {
        // One column: a vertical split whose TOP is a horizontal preview|reader and BOTTOM is the
        // library (icons).
        let nodes = BuiltInWorkspaceLayout.transcribe.panes.nodes
        #expect(nodes.count == 1)
        guard case let .split(_, axis, children) = nodes.first, axis == .vertical else {
            Issue.record("transcribe should open with a vertical split"); return
        }
        #expect(children.count == 2)
        #expect(children.first?.kinds == [.preview, .reading])   // top row (a horizontal split)
        #expect(children.last?.kinds == [.library])              // bottom strip
    }

    @Test("Compare is icons along the bottom, TWO previews + a reader above")
    func compareTwoPreviewsOverIcons() {
        let nodes = BuiltInWorkspaceLayout.compare.panes.nodes
        #expect(nodes.count == 1)
        guard case let .split(_, .vertical, children) = nodes.first else {
            Issue.record("compare should open with a vertical split"); return
        }
        // Top row: two previews + a reader (horizontal). Bottom: library icons.
        let previews = allLeaves(BuiltInWorkspaceLayout.compare.panes).filter { $0.kind == .preview }
        #expect(previews.count == 2)
        #expect(children.last?.kinds == [.library])
    }

    @Test("Read renders EXACTLY ONE library leaf (over reader, beside preview)")
    func readRendersExactlyOneLibraryLeaf() {
        // spec panes.read.one-library (CD live 2026-09-16: "Read shows TWO library panes"). The spec
        // is ONE library — over the reader, beside the preview. `readIsLibraryOverReaderBesidePreview`
        // asserts `.kinds`, but that is a SET: a second library leaf would still collapse to the same
        // {.library,.preview,.reading} and pass. Counting LEAVES is the assertion that actually
        // catches a duplicated library in the composition.
        let libraryLeaves = allLeaves(BuiltInWorkspaceLayout.read.panes).filter { $0.kind == .library }
        #expect(
            libraryLeaves.count == 1,
            "Read composes \(libraryLeaves.count) library panes — the spec is exactly one (two libraries in one window is the reported bug)."
        )
    }

    @Test("no built-in composes more than one library pane (the SET test can't see a duplicate)")
    func noBuiltInComposesTwoLibraries() {
        // Strengthens `noBuiltInMountsTwoLibraries` with the exact reason it must hold: two library
        // leaves render two library tables in one window (spec panes.read.one-library) — the leaf
        // COUNT, not the kind-set, is the guard.
        for layout in BuiltInWorkspaceLayout.allCases {
            let count = allLeaves(layout.panes).filter { $0.kind == .library }.count
            #expect(count <= 1, "\(layout.title) composes \(count) library panes — spec is at most one.")
        }
    }

    @Test("no built-in mounts two library panes until the library pane is instance-safe")
    func noBuiltInMountsTwoLibraries() {
        // The library content view loops when mounted twice in one window (shared data/selection +
        // focused-value collision → the ⌘⌥4 beachball). Until that's fixed at the source, a DATA
        // guard keeps every default to at most one library pane — the reliability line.
        for layout in BuiltInWorkspaceLayout.allCases {
            let libraryCount = allLeaves(layout.panes).filter { $0.kind == .library }.count
            #expect(libraryCount <= 1, "\(layout.title) mounts \(libraryCount) library panes — it will loop")
        }
    }

    /// Every leaf's (id, kind), splits flattened — for the instance-safety guard, which reasons
    /// about which panes publish window-scoped focus keys.
    private func allLeafIDs(_ list: PaneList) -> [(id: UUID, kind: PaneKind)] {
        var out: [(id: UUID, kind: PaneKind)] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(id, kind, _, _): out.append((id: id, kind: kind))
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        list.nodes.forEach(walk)
        return out
    }

    @Test("every built-in is instance-safe: at most one PRIMARY pane per kind")
    func everyBuiltInIsInstanceSafe() {
        // The structural guard that replaces "no two libraries" (spec panes.instance-safe): a
        // window-scoped focused value admits ONE publisher per key, so a workspace with two
        // same-kind panes must flag every duplicate secondary (PaneList.secondaryLeafIDs →
        // \.isSecondarySplitPane). This asserts the model half directly: among the leaves that
        // are NOT flagged secondary (the primaries — the publishers), each kind appears at most
        // once. If it doesn't, that layout WILL loop the scene graph. Deterministic, pure, and
        // canvas-bug-immune (a Scene-less ImageRenderer can't reproduce the focused-value fault).
        for layout in BuiltInWorkspaceLayout.allCases {
            let panes = layout.panes
            let secondary = panes.secondaryLeafIDs()
            let primaries = allLeafIDs(panes).filter { !secondary.contains($0.id) }
            var perKind: [PaneKind: Int] = [:]
            for pane in primaries { perKind[pane.kind, default: 0] += 1 }
            for (kind, count) in perKind {
                #expect(count == 1, "\(layout.title) has \(count) primary \(kind) panes — it will loop")
            }
        }
    }

    @Test("Compare flags the second preview secondary (only one publisher per key)")
    func compareFlagsDuplicatesSecondary() {
        // Compare mounts two previews; the SECOND must be secondary so only one publishes the
        // window-scoped preview focus keys (the focused-value instance-safety fix).
        let panes = BuiltInWorkspaceLayout.compare.panes
        #expect(panes.secondaryLeafIDs().count == 1)
        let secondaryKinds = allLeafIDs(panes)
            .filter { panes.secondaryLeafIDs().contains($0.id) }
            .map(\.kind)
        #expect(Set(secondaryKinds) == [.preview])
    }

    @Test("Transcribe·Tall is three-long (page · word-boxes · editor) over the icon strip")
    func transcribeTallIsThreeLong() {
        // CD 2026-09-16: the detailed-transcription triptych — page, its word-box overlay, and the
        // editor across the top, over the library strip.
        let nodes = BuiltInWorkspaceLayout.transcribeTall.panes.nodes
        #expect(nodes.count == 1)
        guard case let .split(_, .vertical, children) = nodes.first else {
            Issue.record("Transcribe·Tall should open with a vertical split"); return
        }
        #expect(children.first?.kinds == [.preview, .reading])  // three-long top row
        #expect(children.last?.kinds == [.library])             // icon strip below
        // Two previews across the top; the middle one carries the word-box overlay.
        let previews = allLeaves(BuiltInWorkspaceLayout.transcribeTall.panes).filter { $0.kind == .preview }
        #expect(previews.count == 2)
        #expect(previews.contains { $0.config.previewWordBoxes == true })
    }

    @Test("the library strip is a NARROW pinned pane in Transcribe/Tall/Compare, not a normal column")
    func stripLibraryIsPinnedNarrow() {
        // CD 2026-09-16: "the library at the bottom [should be] just icons, and very narrow, like a
        // film script — say 72px." The strip is the LAST child of a vertical split and must carry a
        // small `paneExtent`; without it the strip flexed to ~2/3 of the height (the reported bug).
        for layout in [BuiltInWorkspaceLayout.transcribe, .transcribeTall, .compare] {
            let strip = allLeaves(layout.panes).first { $0.kind == .library }
            #expect(strip?.config.paneExtent == 72, "\(layout.title)'s library strip must pin ~72pt")
            #expect(strip?.config.libraryLayout == "icons", "\(layout.title)'s strip is icons")
        }
        // Browse's library is a NORMAL column (icons, but not a pinned strip) — a strip pin there
        // would shrink a real column to a sliver.
        let browseLibrary = allLeaves(BuiltInWorkspaceLayout.browse.panes).first { $0.kind == .library }
        #expect(browseLibrary?.config.paneExtent == nil, "Browse's library is a column, not a strip")
    }

    @Test("changing a leaf's kind touches only that leaf, preserving id/scope/config")
    func changingLeafKindIsPerPane() {
        // spec panes.head.kind-switch — the head kind menu must change ONLY the clicked pane
        // (the same per-pane discipline as close/split), preserving its identity.
        let panes = BuiltInWorkspaceLayout.read.panes
        let target = allLeafIDs(panes).first { $0.kind == .reading }!
        let changed = panes.changingLeafKind(target.id, to: .inspector)
        // The reader became an inspector; the same id survived; everything else is untouched.
        let changedLeaves = allLeafIDs(changed)
        #expect(changedLeaves.first { $0.id == target.id }?.kind == .inspector)
        #expect(changed.kinds.contains(.inspector))
        #expect(!changed.kinds.contains(.reading))
        // Library + preview are still there, unchanged.
        #expect(changed.kinds.contains(.library))
        #expect(changed.kinds.contains(.preview))
    }

    @Test("no built-in docks an inspector (it's an add-on pane, not a default)")
    func noBuiltInDocksInspector() {
        // CD 2026-09-16: Inspector stays as an available RIGHT-docked pane, but none of the five
        // defaults mount one (Catalogue/Claims, which used to, are gone).
        for layout in BuiltInWorkspaceLayout.allCases {
            #expect(!layout.panes.kinds.contains(.inspector), "\(layout.title) should not dock an inspector")
        }
    }

    @Test("every default round-trips through JSON (a workspace is a PaneList)")
    func everyDefaultRoundTrips() throws {
        for layout in BuiltInWorkspaceLayout.allCases {
            // `.panes` now mints STABLE ids (SF6 fix, below) so this could compare two separate
            // `.panes` calls directly — captured once anyway, since that's the more focused test
            // of what THIS test is actually about (JSON round-tripping).
            let panes = layout.panes
            let decoded = try JSONDecoder().decode(PaneList.self, from: JSONEncoder().encode(panes))
            #expect(decoded == panes, "\(layout.title) should round-trip")
        }
    }

    // MARK: - Stable ids (SF6 review finding)

    @Test("a built-in's ids are STABLE across repeated accesses, not re-minted each time")
    func builtInIdsAreStableAcrossAccesses() {
        // Before the fix: `.panes` called `.leaf`/`.split` (plain, random-UUID factories) fresh on
        // every access, so two calls for the SAME built-in never matched. `WorkspaceSplitStack`/
        // `PaneSpec` key a dragged divider's width and a pane's own split state off a leaf's id —
        // re-deriving Read (navigating away and back, or a relaunch re-seeding from
        // `BuiltInWorkspaceLayout.read.panes`) silently lost every drag and orphaned storage keys.
        for layout in BuiltInWorkspaceLayout.allCases {
            let first = Set(allLeafIDs(layout.panes).map(\.id))
            let second = Set(allLeafIDs(layout.panes).map(\.id))
            #expect(first == second, "\(layout.title)'s leaf ids must be identical across two accesses")
        }
    }

    @Test("different built-ins never share an id")
    func differentBuiltInsHaveDifferentIds() {
        var seen: Set<UUID> = []
        for layout in BuiltInWorkspaceLayout.allCases {
            let ids = Set(allLeafIDs(layout.panes).map(\.id))
            #expect(seen.isDisjoint(with: ids), "\(layout.title) shares an id with an earlier built-in")
            seen.formUnion(ids)
        }
    }

    @Test("splitting a built-in's leaf still mints a FRESH id for the new duplicate")
    func splittingABuiltInLeafStillMintsAFreshId() {
        // The stable-id fix is for the BUILT-IN DEFINITION only — a runtime split/toggle must
        // still get a genuinely fresh identity, or two split-created panes of the same kind would
        // collide instead of coexisting (spec panes.instance-safe).
        let panes = BuiltInWorkspaceLayout.read.panes
        let originalIDs = Set(allLeafIDs(panes).map(\.id))
        let target = allLeafIDs(panes).first { $0.kind == .library }!
        let split = panes.splittingLeaf(target.id, axis: .horizontal)
        let newIDs = Set(allLeafIDs(split).map(\.id)).subtracting(originalIDs)
        #expect(newIDs.count == 1, "splitting should add exactly one brand-new leaf id")
    }

    @Test("removing a built-in's leaf leaves every OTHER leaf's stable id untouched")
    func removingABuiltInLeafKeepsOtherIdsStable() {
        let panes = BuiltInWorkspaceLayout.read.panes
        let target = allLeafIDs(panes).first { $0.kind == .preview }!
        let after = panes.removingLeaf(target.id)
        let survivingIDs = Set(allLeafIDs(after).map(\.id))
        let expected = Set(allLeafIDs(panes).map(\.id)).subtracting([target.id])
        #expect(survivingIDs == expected)
    }

    // MARK: - #4884: Read must not change

    @Test("Read's library leaf sets no explicit content kind — it follows the window, unchanged")
    func readLibraryLeafHasNoExplicitContentKind() {
        let libraryLeaves = allLeaves(BuiltInWorkspaceLayout.read.panes).filter { $0.kind == .library }
        #expect(libraryLeaves.count == 1)
        #expect(
            libraryLeaves.first?.config.libraryContentKind == nil,
            "Read's library leaf must have no explicit kind, or LibraryView.effectiveKind would stop following the window's sidebar collection for it — a real behavior change #4884 must not cause"
        )
    }
}
