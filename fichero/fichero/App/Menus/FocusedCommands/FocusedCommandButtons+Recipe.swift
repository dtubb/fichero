import FicheroAPIClient
import OSLog
import SwiftUI

private let findDocumentsLogger = Logger(subsystem: "app.fichero.fichero", category: "FindDocuments")

// The Project menu's recipe verbs (menus-and-commands spec, ruled 2026-10-10): Set Up…, Start, and
// each stage's verbs. Every verb here is ONE component that the menu bar and any context menu render,
// so a verb has one label, one icon and one action wherever it appears (`menus.context-matches-bar`).
// A verb that cannot act is disabled and says why underneath, the Segment menu's pattern.

// MARK: - The recipe's stages, in order

/// The stages of a recipe, in the order the recipe runs them. The Project menu has one titled section per
/// stage, in this order; a stage shows only once it has a verb in the app.
enum ProjectMenuStage: String, CaseIterable, Identifiable {
    case read = "Read"
    case organise = "Organise"
    case structure = "Structure"
    case connect = "Connect"
    case train = "Train"

    var id: String { rawValue }
    var title: String { rawValue }
}

// MARK: - What the Project menu acts on

/// What the key window offers the Project menu: its project, and what Find the Documents would act on.
/// Published by `ContentView` (below). Equatable on the project and the scope only: the library
/// reference is the same object for one project id, so comparing it would only republish.
struct ProjectMenuTarget: Equatable {
    let projectId: UUID
    let library: LibraryManager.LibraryReference?
    /// The folders, or the pages, Find the Documents would look through; empty when nothing fits.
    let findDocumentsScope: [String]

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.projectId == rhs.projectId && lhs.findDocumentsScope == rhs.findDocumentsScope
    }
}

extension FocusedValues {
    @Entry var projectMenu: ProjectMenuTarget?
}

// MARK: - Set Up…

/// Set Up… for the key window's project: the same setup as Inspector › Recipe › Set Up…
/// (`source.onboard.reachable`, #5421).
struct FocusedSetUpButton: View {
    @FocusedValue(\.setUpProjectAction) private var setUpProjectAction

    var body: some View {
        Button("Set Up…") { setUpProjectAction?.run() }
            .disabled(setUpProjectAction == nil)
        if setUpProjectAction == nil {
            Text("Open a project to set it up")
        }
    }
}

// MARK: - Start

/// Start (⇧⌘↩): the first yes for the key window's project — the same call setup's Start makes
/// (`RecipeSetupStore.start`, `source.project.automatic-after-first-yes`). When the plan is not read yet,
/// the press reads it first; when the plan cannot start, Set Up… opens so its steps say why.
struct FocusedStartRecipeButton: View {
    @FocusedValue(\.projectMenu) private var target
    @FocusedValue(\.setUpProjectAction) private var setUpProjectAction
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let store = target?.library?.recipeSetupStore
        let reason = Self.disabledReason(hasProject: store != nil, plan: store?.startPlan)
        Button("Start") {
            guard let store, let projectId = target?.projectId else { return }
            Task { await start(store, projectId: projectId) }
        }
        .keyboardShortcut(.return, modifiers: [.command, .shift])
        .disabled(reason != nil)
        if let reason {
            Text(reason)
        }
    }

    /// Why Start cannot act, or nil when it can. A plan not read yet is not a reason: the press reads it.
    static func disabledReason(hasProject: Bool, plan: Components.Schemas.StartPlan?) -> String? {
        guard hasProject else { return "Open a project to start its recipe" }
        guard let plan else { return nil }
        if let refusal = plan.refusals.first { return refusal }
        if plan.workflows.isEmpty { return "Nothing to run yet — Set Up… chooses the steps" }
        return nil
    }

    private func start(_ store: RecipeSetupStore, projectId: UUID) async {
        if store.startPlan == nil { await store.loadStartPlan() }
        guard store.canStart else {
            setUpProjectAction?.run()
            return
        }
        guard await store.start() else { return }
        // Land on the run Start queued, as setup's Start does (#5576).
        #if os(macOS)
        if let selection = FirstRunWindow.startedRunSelection(jobId: store.startedRunJobId, projectId: projectId) {
            ActivityWindowSelectionState.shared.select(selection)
            openWindow(id: ActivityWindowSelectionState.detailWindowID)
        }
        #endif
    }
}

// MARK: - Organise › Find the Documents

/// What Find the Documents looks through (#5550). Pure, so every surface agrees.
enum FindDocumentsScope {
    /// A context menu: the selection when the clicked item is one of several selected (Finder
    /// semantics), else the clicked folder; nothing for a lone page, which has no documents to find.
    static func forClick(on id: String, isFolder: Bool, selection: Set<String>) -> [String] {
        if selection.contains(id) && selection.count > 1 { return selection.sorted() }
        return isFolder ? [id] : []
    }

    /// The menu bar: several selected items; or the one selected folder; or, with nothing selected,
    /// the folder the window shows.
    static func forSelection(
        _ selection: Set<String>, shownFolderId: String?, isFolder: (String) -> Bool
    ) -> [String] {
        if selection.count > 1 { return selection.sorted() }
        if let only = selection.first { return isFolder(only) ? [only] : [] }
        if let shownFolderId, isFolder(shownFolderId) { return [shownFolderId] }
        return []
    }
}

/// THE Find the Documents item: the one label and the one action, rendered by the Project menu and by the
/// library's and the sidebar's context menus. One background job; Activity shows it, and the folder
/// updates as it accepts.
struct FindDocumentsMenuItem: View {
    let scopeIds: [String]
    let library: LibraryManager.LibraryReference?

    var body: some View {
        Button {
            Self.run(scopeIds: scopeIds, library: library)
        } label: {
            Label("Find the Documents", systemImage: "doc.on.doc")
        }
        .disabled(scopeIds.isEmpty || library == nil)
    }

    static func run(scopeIds: [String], library: LibraryManager.LibraryReference?) {
        guard let library, !scopeIds.isEmpty else { return }
        Task {
            do {
                _ = try await library.documentService.findDocuments(scopeIds: scopeIds)
            } catch {
                findDocumentsLogger.error("Find the Documents failed: \(error.localizedDescription, privacy: .public)")
                library.documentStore.error = error
            }
        }
    }
}

/// Project › Organise › Find the Documents (⇧⌘D) on the key window's selection. Not ⌥⌘K, which the
/// Preview's Check markup tool has (`PreviewMarkupToolsRow`). The chord is here, on the menu bar's
/// item, not on the shared item: a context menu shows no chords.
struct FocusedFindDocumentsButton: View {
    @FocusedValue(\.projectMenu) private var target

    var body: some View {
        let scope = target?.findDocumentsScope ?? []
        FindDocumentsMenuItem(scopeIds: scope, library: target?.library)
            .keyboardShortcut("d", modifiers: [.command, .shift])
        if target == nil {
            Text("Open a project to find its documents")
        } else if scope.isEmpty {
            Text("Select a folder, or several pages")
        }
    }
}

// MARK: - The publisher

extension ContentView {
    /// The Project menu's target for this window: its project, and Find the Documents' scope over the
    /// library selection, else the folder the sidebar shows.
    var projectMenuTarget: ProjectMenuTarget {
        let shownFolderId: String? = {
            if case .document(let id) = sidebarSelectionState.selectedDestination { return id }
            return nil
        }()
        let store = documentStore
        let scope = FindDocumentsScope.forSelection(browserSelection, shownFolderId: shownFolderId) { id in
            let document = store.currentDocuments.first { $0.id == id }
                ?? store.childrenCache.values.lazy.flatMap({ $0 }).first { $0.id == id }
            return document?.docType == .folder
        }
        return ProjectMenuTarget(
            projectId: windowState.libraryId,
            library: libraryManager.getLibrary(id: windowState.libraryId),
            findDocumentsScope: scope
        )
    }
}
