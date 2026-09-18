import Foundation
import OSLog

private let workspaceSnapshotDecodeLogger = Logger(subsystem: "app.fichero.fichero", category: "WindowWorkspace")

// MARK: - Window workspaces (Daniel, 2026-08-29)
//
// Xcode 27's saveable workspaces are the model: a workspace names the
// window's pane ARRANGEMENT — which panes are visible, their widths, any
// per-slot kind overrides and splits, and the view mode — so a researcher
// can flip between "reading" and "everything" layouts without re-dragging
// dividers. Pure Codable types here; persistence lives in
// `WindowWorkspaceStore`, application in `ContentView+LayoutChooser`.

/// One SplittablePane's split counts, serialisable. Mirrors the live
/// `SplitPaneState` counts (the pane itself stays the single owner of the
/// live state — see `PaneSplitCoordinator`).
struct PaneSplitCounts: Codable, Equatable, Sendable {
    var vertical: Int = 1
    var horizontal: Int = 1

    var isSplit: Bool { vertical > 1 || horizontal > 1 }

    /// The same bounds `SplitPaneState` enforces interactively: each axis
    /// 1...3, capped at 2 per axis while both axes are live (the 2×2 grid).
    /// Applied when a workspace writes counts back so a hand-edited or stale
    /// snapshot can never put a pane in a state the UI cannot reach.
    var sanitized: PaneSplitCounts {
        var counts = PaneSplitCounts(
            vertical: min(max(vertical, 1), 3),
            horizontal: min(max(horizontal, 1), 3)
        )
        if counts.vertical > 1 && counts.horizontal > 1 {
            counts.vertical = min(counts.vertical, 2)
            counts.horizontal = min(counts.horizontal, 2)
        }
        return counts
    }
}

/// The six pane-visibility flags as one value — what a layout PRESET decides
/// (a preset never touches widths, overrides, or splits; those are the saved
/// workspace's job).
struct PaneVisibilityPlan: Codable, Equatable, Sendable {
    var showSidebar: Bool
    var showInspector: Bool
    var showLibraryPane: Bool
    var showPreviewPane: Bool
    var showReaderPane: Bool
    var showChatPane: Bool

    /// At least one CONTENT pane stays on, mirroring the #1696 invariant —
    /// a plan that hides everything is not applyable.
    var isValid: Bool { showLibraryPane || showPreviewPane || showReaderPane }
}

/// Which of the window toolbar's OPTIONAL items are on show (Daniel,
/// 2026-08-31: "can it control the top toolbar buttons to show, and can we
/// have some defaults?").
///
/// The toolbar is BUILT by `ContentView+Toolbar`, so visibility is decided
/// declaratively there — SwiftUI exposes no API for reading or writing an
/// `NSToolbar`'s user customisation set, and reaching into its private
/// defaults would be exactly the hack this app does not ship. Only items a
/// window can live without appear here: the Workspaces menu itself is always
/// present, so a plan can never hide the control that restores the rest.
struct ToolbarVisibilityPlan: Codable, Equatable, Sendable {
    /// Back/forward history buttons (the navigation zone).
    var showNavigation: Bool = true
    /// The Library/Preview/Reader/Chat pane-toggle group.
    var showPaneToggles: Bool = true
    /// LEGACY, decode-only (Daniel, 2026-09-01). Split/New Tab and Layouts
    /// stopped being toolbar items of their own when they became sections of
    /// the Workspaces menu, so nothing gates on these any more. They stay in
    /// the shape so workspaces saved before the merge still decode, and so a
    /// round-trip of an old file does not silently drop keys.
    var showSplitMenu: Bool = true
    var showLayoutsMenu: Bool = true

    /// Everything on — what a fresh window gets.
    static let everything = ToolbarVisibilityPlan()

    /// The reading-desk toolbar: panes and history, none of the arranging
    /// controls (they stay reachable from the Workspaces menu and View menu).
    static let minimal = ToolbarVisibilityPlan(
        showNavigation: true,
        showPaneToggles: true,
        showSplitMenu: false,
        showLayoutsMenu: false
    )
}

extension ToolbarVisibilityPlan {
    /// Lenient decode: a workspace saved before an item existed keeps that
    /// item ON rather than failing the whole catalog (the alternative is a
    /// nil catalog and a user's saved layouts silently gone).
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        showNavigation = try container.decodeIfPresent(Bool.self, forKey: .showNavigation) ?? true
        showPaneToggles = try container.decodeIfPresent(Bool.self, forKey: .showPaneToggles) ?? true
        showSplitMenu = try container.decodeIfPresent(Bool.self, forKey: .showSplitMenu) ?? true
        showLayoutsMenu = try container.decodeIfPresent(Bool.self, forKey: .showLayoutsMenu) ?? true
    }
}

/// Everything a saved workspace restores about a window's arrangement.
/// Widths are points; `paneKindOverrides` and `splits` are keyed by the
/// pane-slot ids the live layout already uses (`PaneSpec.id` and the
/// `"<slot>-<kind>"` split keys respectively).
struct WindowLayoutSnapshot: Codable, Equatable, Sendable {
    var panes: PaneVisibilityPlan
    var libraryPaneWidth: Double
    var readerPaneWidth: Double
    var chatPaneWidth: Double
    var paneKindOverrides: [String: String] = [:]
    var splits: [String: PaneSplitCounts] = [:]
    var viewDisplayMode: String
    var layoutMode: String
    /// Which optional toolbar buttons the arrangement shows (2026-08-31).
    var toolbar: ToolbarVisibilityPlan = .everything
    /// The window-level workflow bar — chrome, like the panes, so a
    /// "Cataloguing" arrangement can bring it with it.
    var showWorkflowBar: Bool = false
    /// The window-level markup bar, for the same reason (Daniel, 2026-09-02:
    /// applying a workspace "doesn't seem to do much"). It was the ONE piece
    /// of window chrome a workspace named nothing about, so a reading
    /// arrangement saved with the markup bar up came back without it — and a
    /// restore that silently drops something is exactly what makes the whole
    /// feature feel inert.
    var showAnnotationBar: Bool = false
    /// The applied window composition (#4686, spec workspaces.one-system: "user workspaces are
    /// saved PaneLists"). This is the field that was MISSING — `panes`/`paneKindOverrides`/`splits`
    /// above are the legacy Bool-visibility shape, so "Save Current as Workspace…" captured a lie
    /// and applying a saved workspace never touched `activePaneList`. `nil` for any snapshot saved
    /// before this field existed (it's a brand-new coding key, so old JSON simply lacks it) —
    /// `applyLayoutSnapshot` falls back to the Read default and logs rather than crashing.
    var paneList: PaneList?
}

extension WindowLayoutSnapshot {
    /// Lenient decode, for the same reason `ToolbarVisibilityPlan`'s is:
    /// fields added after a workspace was saved fall back to their defaults
    /// instead of throwing away every saved layout the user has.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        panes = try container.decode(PaneVisibilityPlan.self, forKey: .panes)
        libraryPaneWidth = try container.decode(Double.self, forKey: .libraryPaneWidth)
        readerPaneWidth = try container.decode(Double.self, forKey: .readerPaneWidth)
        chatPaneWidth = try container.decode(Double.self, forKey: .chatPaneWidth)
        paneKindOverrides = try container.decodeIfPresent(
            [String: String].self, forKey: .paneKindOverrides
        ) ?? [:]
        splits = try container.decodeIfPresent(
            [String: PaneSplitCounts].self, forKey: .splits
        ) ?? [:]
        viewDisplayMode = try container.decode(String.self, forKey: .viewDisplayMode)
        layoutMode = try container.decode(String.self, forKey: .layoutMode)
        toolbar = try container.decodeIfPresent(
            ToolbarVisibilityPlan.self, forKey: .toolbar
        ) ?? .everything
        showWorkflowBar = try container.decodeIfPresent(Bool.self, forKey: .showWorkflowBar) ?? false
        showAnnotationBar = try container.decodeIfPresent(
            Bool.self, forKey: .showAnnotationBar) ?? false
        // A brand-new key (#4686): absent from every snapshot saved before this change, so
        // `decodeIfPresent` alone already returns nil for them — no shape migration needed for
        // ABSENCE. But `decodeIfPresent` still THROWS when the key is PRESENT with malformed data
        // (SF10 review finding), and this whole `init(from:)` runs inside
        // `WindowWorkspaceCatalog.decoded(from:)`'s `try? JSONDecoder().decode(...)` — a throw here
        // propagates up and voids the ENTIRE catalog, deleting every OTHER saved workspace because
        // one has a bad pane list. `try?` locally so a malformed `paneList` degrades to nil (this
        // one snapshot falls back to Read on apply, per `applyLayoutSnapshot`) instead of taking
        // the whole catalog down with it — the same leniency contract every field above already has.
        if let decoded = try? container.decodeIfPresent(PaneList.self, forKey: .paneList) {
            paneList = decoded
        } else {
            workspaceSnapshotDecodeLogger.notice(
                "A saved workspace's pane list failed to decode — treating it as absent rather than losing the whole catalog.")
            paneList = nil
        }
    }
}

/// A named, saved arrangement. `id` is stable across re-saves of the same
/// name so menu identity does not churn.
struct SavedWindowWorkspace: Codable, Equatable, Identifiable, Sendable {
    let id: UUID
    var name: String
    var savedAt: Date
    var layout: WindowLayoutSnapshot

    /// A glyph for the menu row (Daniel, 2026-09-02: "add icons to the menu
    /// rows"). DERIVED from what the arrangement actually is, never stored: a
    /// saved workspace has no icon of its own to persist, and one picked at
    /// save time would go stale the moment the workspace is re-saved.
    var systemImage: String {
        let panes = layout.panes
        if panes.showChatPane { return "sparkles.rectangle.stack" }
        if panes.showReaderPane && !panes.showPreviewPane { return "book" }
        if layout.showWorkflowBar { return "tray.full" }
        if panes.showPreviewPane && panes.showReaderPane { return "rectangle.split.3x1" }
        if !panes.showPreviewPane && !panes.showReaderPane { return "sidebar.left" }
        return "rectangle.grid.1x2"
    }

    /// What applying it will actually do, in the row's own tooltip. Daniel's
    /// 2026-09-02 reading of the menu was that applying a workspace "doesn't
    /// seem to do much" — a row that lists what it is about to restore is
    /// half the answer to that, and the other half is restoring it.
    var help: String {
        var parts: [String] = []
        let panes = layout.panes
        var visible: [String] = []
        if panes.showSidebar { visible.append("sidebar") }
        if panes.showLibraryPane { visible.append("library") }
        if panes.showPreviewPane { visible.append("preview") }
        if panes.showReaderPane { visible.append("reader") }
        if panes.showChatPane { visible.append("chat") }
        if panes.showInspector { visible.append("inspector") }
        parts.append(visible.isEmpty ? "no panes" : visible.joined(separator: ", "))
        if layout.showWorkflowBar { parts.append("workflow bar") }
        if layout.showAnnotationBar { parts.append("markup bar") }
        if !layout.splits.isEmpty {
            let count = layout.splits.count
            parts.append(count == 1 ? "1 split pane" : "\(count) split panes")
        }
        return "Restores: " + parts.joined(separator: " · ")
    }
}

/// The app-wide list of saved workspaces (workspaces apply per window but the
/// CATALOG is shared, like Xcode's). Pure value + JSON round-trip; the store
/// owns UserDefaults.
struct WindowWorkspaceCatalog: Codable, Equatable, Sendable {
    var version: Int = 1
    var workspaces: [SavedWindowWorkspace] = []

    /// Save under `name`: a new name appends, an existing name (compared
    /// case-insensitively, whitespace-trimmed) is UPDATED in place keeping
    /// its identity — "Save Workspace…" with an old name means "overwrite
    /// mine", not "make a confusing twin". Returns nil for an empty name.
    @discardableResult
    mutating func save(
        name rawName: String,
        layout: WindowLayoutSnapshot,
        at date: Date = Date(),
        id: UUID = UUID()
    ) -> SavedWindowWorkspace? {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        if let index = workspaces.firstIndex(where: {
            $0.name.compare(name, options: [.caseInsensitive]) == .orderedSame
        }) {
            workspaces[index].name = name
            workspaces[index].savedAt = date
            workspaces[index].layout = layout
            return workspaces[index]
        }
        let workspace = SavedWindowWorkspace(id: id, name: name, savedAt: date, layout: layout)
        workspaces.append(workspace)
        workspaces.sort { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        return workspace
    }

    mutating func remove(id: UUID) {
        workspaces.removeAll { $0.id == id }
    }

    /// Rename the workspace with `id`, keeping its identity, layout and saved
    /// date — for the Workspace Manager's rename field. Returns the updated
    /// workspace, or nil when: the name is empty, no workspace has that id, or
    /// ANOTHER workspace already wears that name (case-insensitive) — the same
    /// confusing-twin guard `save` applies, refused here rather than merged
    /// because a rename must not silently swallow a second arrangement. Re-sorts
    /// by name so the menus stay alphabetical.
    @discardableResult
    mutating func rename(id: UUID, to rawName: String) -> SavedWindowWorkspace? {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        guard workspaces.contains(where: { $0.id == id }) else { return nil }
        let collides = workspaces.contains {
            $0.id != id && $0.name.compare(name, options: [.caseInsensitive]) == .orderedSame
        }
        guard !collides else { return nil }
        for index in workspaces.indices where workspaces[index].id == id {
            workspaces[index].name = name
        }
        workspaces.sort { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        return workspaces.first { $0.id == id }
    }

    func encoded() throws -> Data {
        try JSONEncoder().encode(self)
    }

    /// nil (never a silent empty catalog) when the data does not decode —
    /// the caller decides whether starting fresh is acceptable.
    static func decoded(from data: Data) -> WindowWorkspaceCatalog? {
        try? JSONDecoder().decode(WindowWorkspaceCatalog.self, from: data)
    }
}

// MARK: - Layout presets (the Views chooser) — DELETED (#4685)
//
// `WindowLayoutPreset` ("Library Only / Reading / Everything") was a SECOND built-in
// arrangement system parallel to `BuiltInWorkspaceLayout` — the exact "two systems for one
// job" the spec's workspaces.one-system ruling closes. Zero callers remained once
// `applyLayoutPreset`/`WindowLayoutCommands.applyPreset` were removed from
// ContentView+LayoutChooser.swift; deleted rather than kept dead.

// MARK: - Split command routing (the Split/Tab toolbar button) — DELETED (#4685)
//
// `SplitCommandRouting.storageKey` minted a `"<slot>-<kind>"` key from `widescreenPaneSpecs`,
// but the applied renderer's slot ids are `"pane-<keyPath>-<kind>"` (paneNodeView) — they never
// matched, so menu Split posted to nothing. Split is now routed through the `PaneList` model
// itself (`activePaneList.splittingLeaf(id, axis:)`, ContentView+LayoutChooser.swift's
// `focusedLeafID`/`splitFocusedLeaf`) — symmetric with how close already worked via
// `removingLeaf`. There is nothing left for this type to route to.
