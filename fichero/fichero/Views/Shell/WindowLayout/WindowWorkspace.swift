import Foundation

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
}

/// A named, saved arrangement. `id` is stable across re-saves of the same
/// name so menu identity does not churn.
struct SavedWindowWorkspace: Codable, Equatable, Identifiable, Sendable {
    let id: UUID
    var name: String
    var savedAt: Date
    var layout: WindowLayoutSnapshot
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

    func encoded() throws -> Data {
        try JSONEncoder().encode(self)
    }

    /// nil (never a silent empty catalog) when the data does not decode —
    /// the caller decides whether starting fresh is acceptable.
    static func decoded(from data: Data) -> WindowWorkspaceCatalog? {
        try? JSONDecoder().decode(WindowWorkspaceCatalog.self, from: data)
    }
}

// MARK: - Layout presets (the Views chooser)

/// The compound layouts the Views-chooser button offers (Xcode's
/// "Editor Only / Canvas / Assistant" idiom): sensible named pane sets, with
/// the user's saved workspaces listed beneath a divider.
enum WindowLayoutPreset: String, CaseIterable, Identifiable, Sendable {
    case libraryOnly
    case reading
    case everything

    var id: String { rawValue }

    var title: String {
        switch self {
        case .libraryOnly: "Library Only"
        case .reading: "Reading"
        case .everything: "Everything"
        }
    }

    var systemImage: String {
        switch self {
        case .libraryOnly: "sidebar.left"
        case .reading: "book"
        case .everything: "rectangle.split.3x1"
        }
    }

    /// The pane set the preset applies. Only visibility — widths, kind
    /// overrides and splits are left exactly as the user has them.
    var plan: PaneVisibilityPlan {
        switch self {
        case .libraryOnly:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: false,
                showReaderPane: false, showChatPane: false
            )
        case .reading:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: true, showChatPane: false
            )
        case .everything:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: true,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: true, showChatPane: true
            )
        }
    }

    /// Whether the window currently shows exactly this preset's pane set —
    /// drives the chooser's checkmark.
    func matches(_ current: PaneVisibilityPlan) -> Bool {
        plan == current
    }
}

// MARK: - Split command routing (the Split/Tab toolbar button)

/// Resolves WHICH SplittablePane a window-level "Split Right/Below" command
/// addresses: the pane that has focus, named by the same
/// `"<slot>-<effectiveKind>"` storage key the live layout mints in
/// `ContentView.kindContent` (slot survives a kind override — 2026-08-24).
/// Pure so the routing is unit-testable without a window.
enum SplitCommandRouting {
    /// - Parameters:
    ///   - focus: the focused pane (`focusedPane ?? paneFocusHint`).
    ///   - slots: the visible centre-row slots in order — (slot id, planned
    ///     kind rawValue), from `widescreenPaneSpecs`.
    ///   - overrides: slot id → overriding kind rawValue (`paneKindOverrides`).
    /// - Returns: the storage key of the focused pane's SplittablePane, or
    ///   nil when focus is on a surface that does not split (sidebar,
    ///   inspector) or the focused kind is not in the row.
    static func storageKey(
        focus: PaneFocus?,
        slots: [(id: String, kind: String)],
        overrides: [String: String]
    ) -> String? {
        guard let targetKind = splitTargetKind(for: focus) else { return nil }
        guard let slot = slots.first(where: { (overrides[$0.id] ?? $0.kind) == targetKind }) else {
            return nil
        }
        return "\(slot.id)-\(targetKind)"
    }

    private static func splitTargetKind(for focus: PaneFocus?) -> String? {
        switch focus {
        case .content: "library"
        case .preview: "preview"
        case .reading: "reading"
        case .chat: "chat"
        case .sidebar, .inspector, nil: nil
        }
    }
}
