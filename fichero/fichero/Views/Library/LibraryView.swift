import Combine
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

enum LibraryContentCollection {
    case documents
    case entities
}

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    let contentCollection: LibraryContentCollection
    let isLoading: Bool
    let isConnected: Bool
    let errorMessage: String?
    let onRetry: () -> Void
    /// Sort field / direction / filter-bar visibility, lifted out of @State so
    /// the in-content mode rail can drive them too (#1477). Owned by ContentView.
    @Bindable var libraryToolbar: LibraryToolbarState
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    var isPaneFocused: Bool = false
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    let folderId: String?  // Current folder ID for per-folder sort persistence
    var onRequestFocus: () -> Void = {}  // Called on tap to pull keyboard focus into content area
    var onRequestPreviousPaneFocus: () -> Void = {}  // Left arrow in list/table — move to sidebar
    var onRequestNextPaneFocus: () -> Void = {}  // Right arrow in list/table — move to inspector
    var onNavigateInto: (Document) -> Void = { _ in }  // Double-click on folder/PDF — navigate into it
    /// Called when a page item row is selected in the outline table (#2405).
    /// Callers should set `pageFocusDocument` to drive reader + inspector focus.
    var onPageFocus: (Document) -> Void = { _ in }
    /// When the sidebar is hidden, single-click in the grid acts like Finder
    /// (no-sidebar fallback): plain click navigates INTO navigable containers
    /// instead of just selecting. Modified clicks (Shift/Cmd) still select
    /// only — you can't have a multi-select if one click navigates away.
    /// (#786)
    var sidebarHidden: Bool = false
    /// Submit handler for the toolbar search field. ContentView wires
    /// this to runToolbarSearch so typing+Return in library mode fires
    /// a global search and switches the sidebar into search mode —
    /// matches the behaviour of every other mode-specific .searchable.
    var onToolbarSearchSubmit: (String) -> Void = { _ in }
    /// Sidebar-parity Add to Chat (#4121): the host opens chat scoped to the
    /// current selection; nil hides the menu item (previews, non-chat hosts).
    var onAddToChat: (() -> Void)?
    /// The engine-search field's text and mode, now that the field lives in
    /// the library's own mini toolbar rather than on the window (#4407).
    /// Defaulted so the previews construct unchanged.
    var searchFieldText: Binding<String> = .constant("")
    var searchFieldMode: Binding<SearchFieldMode> = .constant(.ask)
    /// Summoned search (#4521): the field renders in the mini toolbar only
    /// while this is on. A Binding (not a plain Bool) so the field's own
    /// dismiss affordances can flip it. Defaulted ON so previews and non-shell
    /// hosts keep the field without extra wiring.
    var searchFieldVisible: Binding<Bool> = .constant(true)
    /// The transient search this grid is showing results for, if any (#4403).
    /// Non-nil means the empty state must talk about the SEARCH — never about
    /// choosing a collection, which is what it used to fall back to under a
    /// header reading "3 results for …".
    var activeSearchQuery: String?
    /// What that search matched, per kind. The grid can only render the
    /// document leg, so these are how the body explains a header count it
    /// cannot show.
    var searchHitCounts: SearchHitCounts = SearchHitCounts()
    /// Per-hit matched text + relevance for the active search (#11): rows
    /// show WHY a document matched ("why does 'Colombia' get us this
    /// image?") and its relevance on the right. Empty outside search.
    var searchRowHits: [String: TransientSearchRowHit] = [:]

    @State var searchText: String = ""
    /// Precomputed lowercased ⌘F search keys per docId (#3865). Rebuilt only when
    /// the document set changes, so keystroke filtering is a dict lookup, not a
    /// fresh full-OCR scan. See `rebuildDocumentSearchKeys`.
    @State var documentSearchKeys: [String: String] = [:]
    /// The ONE file-picker presenter every import affordance shares (#4449):
    /// the bottom-bar Import button, and the folder contextual-menu "Import
    /// Here…" item. Originally #2313 for just the bottom bar.
    @State var showingFileImporter = false
    /// The container the in-flight `showingFileImporter` picker imports into.
    /// Set immediately before flipping `showingFileImporter = true` so every
    /// presenter states its own target explicitly — nil silently lands
    /// documents at the library root, which is the "+ on a folder imports to
    /// the root" bug this issue exists to close (#4449).
    @State var fileImportTargetFolderId: String?
    /// Link/Copy/Move for the in-flight `showingFileImporter` picker (#4452)
    /// — the Data-menu Import submenu offers all three; the bottom-bar and
    /// contextual-menu affordances always want `.link` and set this
    /// explicitly rather than relying on the default.
    @State var fileImportMode: IngestMode = .link
    /// Metadata-popover choice (#18): which optional attributes list rows
    /// display. App-wide preference, comma-joined raw values.
    @AppStorage("library.rowAttributes") var rowAttributesRaw: String = LibraryRowAttribute.defaultRaw
    @FocusState var filterFieldFocused: Bool
    /// The summoned engine-search field (#4521). Tracked so the row keyboard
    /// grammar can stand down while the user is TYPING — ancestor `.onKeyPress`
    /// handlers intercept keys before a focused descendant TextField sees
    /// them, so without this guard the search field looked dead (2026-08-11:
    /// "it won't even let me search by typing into search box").
    @FocusState var searchFieldFocused: Bool
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]
    @SceneStorage("library.sortFieldsByFolder") var sortFieldsByFolderJSON: String = "{}"
    @SceneStorage("library.sortAscendingByFolder") var sortAscendingByFolderJSON: String = "{}"

    // Workflow picker state
    @State var showWorkflowPicker = false
    @State var selectedDocumentIdsForBatch: [String] = []

    /// Document pending presentation in the Add-to-Workspace picker (#1494).
    /// Non-nil drives the `.sheet(item:)` below.
    @State var workspacePickerDocument: Document?
    /// Non-nil presents the bookmark sheet for this document (#2755).
    @State var bookmarkPickerDocument: Document?

    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager
    @Environment(WindowState.self) var windowState
    /// Finder-style Open in New Tab / New Window opens a fresh window on the
    /// current library via the Safari new-window path (#1685).
    @Environment(\.openWindow) var openWindow
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(EntityService.self) var entityService
    @Environment(ArtifactService.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    /// A split's SECOND library pane must not write the shared
    /// focusedSceneValue keys — two live writers of the same key is the
    /// "FocusedValue update tried to update multiple times per frame" fault
    /// that recursed scene invalidation at launch (2026-08-12).
    @Environment(\.isSecondarySplitPane) var isSecondarySplitPane
    let featureManager = FeatureManager.shared
    @State var workflowRunProviderCache = WorkflowRunProviderCache.shared

    // Column visibility for Table view (persisted per-window/scene)
    @SceneStorage("column_name") var showName = true
    @SceneStorage("column_status") var showStatus = true
    @SceneStorage("column_progress") var showProgress = true
    @SceneStorage("column_output") var showOutput = true
    @SceneStorage("column_fileType") var showFileType = true
    @SceneStorage("column_path") var showPath = false
    @SceneStorage("column_createdDate") var showCreatedDate = true
    @SceneStorage("column_modifiedDate") var showModifiedDate = false
    @SceneStorage("column_size") var showSize = false
    @SceneStorage("column_artifacts") var showArtifacts = false  // #519: hidden by default

    // Per-entity-type visibility flags for the list-view lozenge rows.
    // Now driven by the same @AppStorage CSV used by the KG ontology
    // browser + document-inspector KG tab so toggling People in any
    // surface affects all of them. The CSV stores HIDDEN EntityType
    // raw values ("person", "location", "organization", "event",
    // "concept", "other"); empty CSV = show everything. (#887)
    @AppStorage("inspector.kg.hiddenKinds") var hiddenKindsCSV: String = ""

    // "dates" doesn't have a KnowledgeEntity counterpart (dates are
    // surfaced via the timeline tool, not as KG entities) so the dates
    // lozenge stays on a Library-only @SceneStorage flag.
    @SceneStorage("list_show_dates") var showDatesEntities = true

    /// Mac-native column customization for the table view (right-click on
    /// any column header → show/hide menu, drag to reorder, drag-resize).
    /// Backed by SwiftUI's TableColumnCustomization API. Persisted via
    /// @SceneStorage (the follow-up the old @State comment promised, #519/
    /// #4160): resize/reorder/show-hide now survive relaunch, per window —
    /// matching how sort already persists.
    @SceneStorage("library.tableColumns")
    var tableColumnCustomization: TableColumnCustomization<LibraryOutlineNode> = .init()

    /// Drives the expandable outline Table (#2258). Lazily created on
    /// first appear (needs the library's entity service from the
    /// environment); caches per-document rollup counts so collapsed rows
    /// can show "12 entities, 3 notes" without fetching the children.
    @State var outlineModel: LibraryOutlineModel?
    /// Disclosure expansion state for the outline Table, keyed by node id
    /// (document id). Expanding a document triggers its rollup fetch.
    @State var outlineExpanded: Set<String> = []
    /// Compact width (iPhone) drops the macOS/iPadOS `DisclosureTableRow`
    /// outline for a plain document list — `Table` disclosure is a
    /// regular-width affordance.
    @Environment(\.horizontalSizeClass) var horizontalSizeClass

    @State var entities: [Components.Schemas.KnowledgeEntity] = []
    // Canvas/spatial selection is NOT separate state: it is `selection`,
    // translated through `canvasSelectedNodeIds` (#4192, widened by #4409).
    @State var cachedLibraryProjection = SpatialLibraryProjection(nodes: [], links: [])

    @State var isLoadingEntities = false
    @State var entityLoadErrorMessage: String?

    /// The one place `handleFileImport` reports an import that did not fully
    /// land (#3276). `errorMessage` above is a `let` supplied by the parent, so
    /// this path had nowhere to write and settled for a log line — which is how
    /// "imported 7 of 10" looked identical to "imported 10". Not `private`:
    /// `handleFileImport` lives in the LibraryView+BottomActionBar.swift
    /// extension, a different file.
    @State var importErrorMessage: String?

    // ponytail: recompute inputs — documents, entities, searchText, sortOrder, sortFieldRaw, sortAscending, folderId
    // Not `private`: recomputeFiltered() lives in the LibraryView+FilterAndBatch.swift
    // extension (a different file), so these must be at least internal to be visible there.
    @State var filteredDocuments: [Document] = []
    @State var filteredEntities: [Components.Schemas.KnowledgeEntity] = []
    /// Stable key for .onChange in iconsView — updated inside recomputeFiltered()
    /// to reset thumbnail prefetch state when the visible document set changes. A
    /// hash of the ids (Int), not a joined String of every id (#3870).
    @State var thumbnailPrefetchKey: Int = 0
    /// id → index in `filteredDocuments`, rebuilt in recomputeFiltered() so
    /// prefetch scheduling is an O(1) lookup, not an O(n) firstIndex per cell (#3870).
    @State var documentIndexById: [String: Int] = [:]
    @State var prefetchedThumbnailIds: Set<String> = []
    @State var thumbnailPrefetchTask: Task<Void, Never>?

    // Delete confirmation state
    @State var showDeleteConfirmation = false
    @State var documentsToDelete: [Document] = []
    // #4198: delete acts on document rows and states what it skips; a
    // child-only selection presents the same dialog as a plain notice
    // instead of a silent no-op.
    @State var deleteSkippedNote: String?

    // Inline rename state
    @State var renamingDocumentId: String?
    @State var editingName: String = ""

    // Miller columns (#4160 step 4): the folder-ID chain below the browsed
    // root (ids, never Document snapshots — every segment resolves through
    // the live children cache each render and truncates when one dies), the
    // active column depth, and the per-folder children cache the column
    // stack's .task fills through DocumentStore.children(of:).
    @State var columnsPath: [String] = []
    @State var columnsActiveDepth: Int = 0
    @State var columnsChildren: [String: [Document]] = [:]

    // Type-to-select state
    @State var typeSelectBuffer: String = ""
    @State var typeSelectTask: Task<Void, Never>?

    // Keyboard scroll target for list view (set by arrow key nav, consumed by ScrollViewReader)
    // listScrollTarget = minimal scroll (anchor: nil) — used by arrow keys so we
    //   don't recenter on every keypress when the new item is already on-screen (#769).
    // listScrollCenterTarget = forced center scroll — used by double-click and other
    //   layout-changing actions where the user genuinely wants the item centered.
    @State var listScrollTarget: String?
    @State var listScrollCenterTarget: String?

    // Selection anchor for Shift+click range select
    @State var selectionAnchor: String?
    // Keyboard cursor (#4160): the row arrow-nav last landed on. The old code
    // used `selection.first` — Set hash order — so after a multi-select the
    // arrows resumed from, Return opened, and the list scrolled to an
    // arbitrary row.
    @State var selectionCursor: String?
    // Space → Quick Look temp-file URL (#4160); non-nil presents the panel.
    @State var quickLookURL: URL?

    // Grid column count for arrow key navigation (updated by GeometryReader in iconsView)
    @State var gridColumnCount: Int = 4

    // Zoom scale for the icon view (persisted per-app)
    @AppStorage("library.iconViewScale") var iconViewScale: Double = 1.0
    // Captures iconViewScale at the start of a pinch so the gesture's
    // multiplier multiplies against the gesture-start size, not the
    // continuously-updating scale (which would compound exponentially).
    @State var pinchBaseScale: Double = 1.0

    // Degraded fallback only: live activity/change-stream signals now trigger
    // the surgical pending-status refresh immediately (#3200). Keep the timer
    // only while live updates are paused/unavailable.
    // STATIC (O4, 2026-08-09): a stored `let` on a View struct re-created —
    // and .autoconnect() re-subscribed — a new publisher on EVERY LibraryView
    // init. One shared publisher serves every instance; the per-view guard
    // below still suppresses the work.

    /// Reentrancy gate for the sort chain (O1/O2, 2026-08-09): a header click
    /// used to run syncServerListingSort + recomputeFiltered THREE times —
    /// sortOrder's handler writes sortFieldRaw/sortAscending, whose handlers
    /// each re-ran the same sync. Writers that already sync set this flag so
    /// the field handlers know the work is covered.
    @State var isApplyingSortChange = false

    /// Rubber-band sweep state (icon mode, 2026-08-09) — an @Observable box
    /// so per-tick rect mutation re-renders only the overlay, never the
    /// grid; see MarqueeModel. Frames stay @State (they change on layout,
    /// not per tick).
    @State var marqueeModel = MarqueeModel()
    @State var iconTileFrames: [String: CGRect] = [:]
}
