import SwiftUI

// MARK: - View Mode Enums

/// Sidebar mode selection - Xcode-style mode switching
/// Search is NOT a mode (#4106/S2): the toolbar search field renders its
/// results into the Library view, so `.search` was retired. ⌘2 stays
/// unassigned rather than renumbering the muscle-memory shortcuts below.
enum SidebarMode: String, CaseIterable {
    case library      // 1: Documents, folders
    case chat         // 3: Conversations
    case workflows    // 4: Workflow definitions
    case automation   // 5: Schedules + triggers
    case activity       // 6: All workflow runs (running + completed + failed) with logs/errors
    case research       // 8: Research projects + workspace
    // `.knowledgeGraph` (9) DELETED (#4705 increment 3, creative director
    // 2026-09-18: "The ⌃⌘1…9 Sidebar-mode entries are removed [for KG now;
    // the rest retire with increments 4-6]") — entity/claim browsing lives
    // in the library-wide Entities/Claims tables. ⌃⌘9 is free; `restored
    // (from:)` below still degrades a persisted "knowledgeGraph" string to
    // `.library` rather than crashing on restore.

    /// SF Symbol icon name for this mode
    var icon: String {
        switch self {
        case .library: "folder"
        case .chat: "bubble.left.and.bubble.right"
        case .workflows: "bolt"
        case .research: "flask"
        case .automation: "gearshape.2"
        case .activity: "clock"
        }
    }

    /// Display label for menus
    var label: String {
        switch self {
        case .library: "Library"
        case .chat: "Chat"
        case .workflows: "Workflows"
        case .research: "Research"
        case .automation: "Automation"
        case .activity: "Activity"
        }
    }

    /// Keyboard shortcut number (1-9)
    var shortcutNumber: String {
        switch self {
        case .library: "1"
        case .chat: "3"
        case .workflows: "4"
        case .automation: "5"
        case .activity: "6"
        case .research: "8"
        }
    }

    /// Tooltip copy: what the mode shows and how to reach it. (#1371)
    var helpText: String {
        let body: String
        switch self {
        case .library:
            body = "Library — browse your documents and folders"
        case .chat:
            body = "Chat — ask questions about your documents in a conversation"
        case .workflows:
            body = "Workflows — build and run AI processing pipelines"
        case .research:
            body = "Research — research projects and their workspace"
        case .automation:
            body = "Automation — schedules and triggers that run workflows automatically"
        case .activity:
            body = "Activity — monitor running and recent background jobs"
        }
        return "\(body) (⌘\(shortcutNumber))"
    }

    /// Tolerant decode for a persisted raw value (#4705 increment 3a) — a
    /// retired case's string (`"knowledgeGraph"`, increment 3b) or anything
    /// else that isn't a current case degrades to `.library` instead of
    /// leaning on `@SceneStorage`'s own unproven `RawRepresentable` fallback
    /// (the #4703 restored-state crash class). Mirrors the existing
    /// `"search"` pattern for `AppViewMode` (`ContentView+Persistence.swift:
    /// 69-72`).
    static func restored(from rawValue: String) -> SidebarMode {
        SidebarMode(rawValue: rawValue) ?? .library
    }
}

/// Library layout modes
enum LibraryLayout: String, CaseIterable, Codable {
    case icons = "Icons"
    case list = "List"
    case table = "Table"
    /// Finder-style Miller column browser (#4160 step 4); the table keeps
    /// its 3-level outline — this is an additional mode, not a replacement.
    case columns = "MillerColumns"
    /// Dataset renderers (Stage 2) — twins of the ViewDisplayMode cases.
    case grid = "DataGrid"
    case cards = "Cards"
    case timeline = "Timeline"
    case calendar = "CalendarGrid"
    case geoMap = "GeoMap"
    case canvas = "Canvas"
    /// The RealityKit 3D "Space" view (#3088). Mirrors `ViewDisplayMode.space`
    /// so the View-menu ⌘5 ↔ toolbar picker bridge stays bijective — without
    /// this case Space would collapse onto `.canvas` and revert on select.
    case space = "Space"

    var icon: String {
        switch self {
        case .icons: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .columns: "rectangle.split.3x1"
        case .grid: "tablecells.badge.ellipsis"
        case .cards: "rectangle.grid.2x2"
        case .timeline: "chart.bar.xaxis"
        case .calendar: "calendar"
        case .geoMap: "mappin.and.ellipse"
        case .canvas: "rectangle.3.group"
        case .space: "cube.transparent"
        }
    }

    /// The `ViewDisplayMode` this menu layout maps to — the inverse of
    /// `ViewDisplayMode.libraryLayout`, the single source of truth for the
    /// LibraryLayout → ViewDisplayMode bridge (#3088).
    var displayMode: ViewDisplayMode {
        switch self {
        case .icons: .icon
        case .list: .list
        case .table: .table
        case .columns: .columns
        case .grid: .grid
        case .cards: .cards
        case .timeline: .timeline
        case .calendar: .calendar
        case .geoMap: .geoMap
        case .canvas: .canvas
        case .space: .space
        }
    }
}

/// Preview panel mode (matches LayoutMode)
enum PreviewMode: String, CaseIterable {
    case none
    case standard   // Content and preview stacked vertically
    case widescreen // Content and preview side-by-side
}

/// Mail-modeled vocabulary for WHERE the document preview sits relative to the
/// library list (#2032/§6d). This is a thin facade over the canonical
/// `PreviewMode` — it does NOT introduce a parallel stored value. The single
/// source of truth remains `ViewSettings.previewMode` (and its per-window
/// `@SceneStorage("currentLayoutMode")` mirror); `PreviewLayout` just renames
/// the three existing cases into Apple-Mail terms:
///
///   .side   ⇆ .widescreen  — list and preview side-by-side (HStack)
///   .bottom ⇆ .standard    — list above, preview below (VSplitView)
///   .hidden ⇆ .none        — list only, no preview
///
/// Default `.side` preserves current behavior (`previewMode` defaults to
/// `.widescreen`). Use `PreviewMode.layout` / `PreviewLayout.previewMode` to
/// bridge; never store a `PreviewLayout` separately.
enum PreviewLayout: String, CaseIterable {
    case side    // = .widescreen
    case bottom  // = .standard
    case hidden  // = .none

    /// The canonical preview mode this layout maps to.
    var previewMode: PreviewMode {
        switch self {
        case .side: .widescreen
        case .bottom: .standard
        case .hidden: .none
        }
    }
}

extension PreviewMode {
    /// The Mail-vocabulary layout this preview mode corresponds to.
    var layout: PreviewLayout {
        switch self {
        case .widescreen: .side
        case .standard: .bottom
        case .none: .hidden
        }
    }
}

// MARK: - Focused Values

/// Focused value for sidebar mode - allows menu commands to change per-window sidebar mode
extension FocusedValues {
    @Entry var sidebarMode: Binding<SidebarMode>?

    /// Per-window inspector visibility, published by the focused ContentView so
    /// the View-menu "Show/Hide Inspector" command toggles only the focused
    /// window — not every open window (#1451).
    @Entry var showInspector: Binding<Bool>?

    /// Per-window visibility of the capability bar, published by the focused
    /// ContentView so View ▸ Show Workflow Bar toggles only that window —
    /// the Preview convention, where a markup bar belongs to the window you
    /// turned it on in (2026-08-28).
    @Entry var showWorkflowBar: Binding<Bool>?

    /// Labels under the workflow bar's glyphs, per window.
    @Entry var showWorkflowBarLabels: Binding<Bool>?

    /// Per-window visibility of the major reading-surface panes, published by
    /// the focused ContentView so the View menu mirrors the toolbar toggles
    /// for each pane (#1215). Same per-window rationale as `showInspector`:
    /// each binds the focused window's @SceneStorage flag.
    @Entry var showDocumentGrid: Binding<Bool>?
    @Entry var showDocumentCanvas: Binding<Bool>?
    /// The WebKit/reading content pane (transcript surface).
    @Entry var showReadingPane: Binding<Bool>?

    /// The active representation shown in the document content/WebKit surface
    /// (Transcript/Digest/Graph/Claims/Timeline/Map), published by the focused
    /// `DocumentKGSurface`. Drives the View-menu "Add View" items so the
    /// representation switcher lives in the menu instead of a floating icon bar
    /// over the content (#2032 / reform §G). Nil when no document surface is
    /// focused, so the menu items disable.
    ///
    /// Uses the Equatable `DocumentRepresentationFocus` wrapper (not a raw
    /// `Binding`, which is non-Equatable) so SwiftUI can dedupe it: a `body`
    /// pass with the same active tab does NOT republish, avoiding per-frame
    /// focused-value churn (#2032).
    @Entry var documentRepresentation: DocumentRepresentationFocus?

    // `knowledgeGraphViewMode` DELETED (#4705 increment 3): it published the
    // focused `OntologyBrowser`'s own List/Graph/Chart/Timeline/Map mode,
    // consumed only by the now-deleted `KnowledgeGraphViewModeSection`
    // (`ViewMenuLayoutSections.swift`). `KnowledgeGraphViewModeFocus` was
    // defined in `OntologyBrowser.swift` and retires with it.
}
