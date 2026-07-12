import FicheroAPIClient
import Foundation
import Observation
import SwiftUI

/// Shared selection holder for the document List + detail slice (#2002).
///
/// The list writes the selected document snapshot; the torn-off window reads
/// the same shared value so it follows selection without extra plumbing.
@Observable
@MainActor
final class FocusedDocument {
    static let shared = FocusedDocument()

    var id: String?
    var libraryId: UUID?
    private(set) var document: Document?

    init() {}

    func select(_ document: Document?, libraryId: UUID?) {
        id = document?.id
        self.libraryId = libraryId
        self.document = document
    }

    func clear() {
        id = nil
        libraryId = nil
        document = nil
    }
}

/// Detached document detail window for the list/detail slice (#2002).
struct DocumentDetailWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(ClaimFocusState.self) private var claimFocusState
    @Environment(KGFocusState.self) private var kgFocusState

    @State private var focused = FocusedDocument.shared
    @State private var isPinned = false
    @State private var pinnedDocument: Document?
    @State private var windowState = WindowState(libraryId: FocusedDocument.shared.libraryId ?? UUID())

    private var activeLibrary: LibraryManager.LibraryReference? {
        if let libraryId = focused.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }

    private var shownDocument: Document? {
        isPinned ? pinnedDocument : focused.document
    }

    var body: some View {
        Group {
            if let library = activeLibrary, let shownDocument {
                documentInspector(for: shownDocument, library: library)
            } else {
                ContentUnavailableView(
                    "Document",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text("Select a document to inspect it.")
                )
            }
        }
        .navigationTitle(shownDocument?.name ?? "Document")
        .navigationSubtitle(activeLibrary?.displayName ?? "")
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Toggle(isOn: $isPinned) {
                    Label(
                        isPinned ? "Pinned" : "Following selection",
                        systemImage: isPinned ? "pin.fill" : "pin"
                    )
                }
                .toggleStyle(.button)
                .help(
                    isPinned
                        ? "Pinned to this document — won't follow selection"
                        : "Follow the current document selection"
                )
                .onChange(of: isPinned) { _, pinned in
                    pinnedDocument = pinned ? focused.document : nil
                }
            }
        }
        .frame(minWidth: 360, minHeight: 420)
        .onAppear {
            if let library = activeLibrary {
                windowState.libraryId = library.id
            }
        }
        .onChange(of: focused.libraryId) { _, newLibraryId in
            if let newLibraryId {
                windowState.libraryId = newLibraryId
            }
        }
    }

    @ViewBuilder
    private func documentInspector(
        for document: Document,
        library: LibraryManager.LibraryReference
    ) -> some View {
        DocumentInspector(document: document)
            .environment(library.entityService)
            .environment(library.artifactService)
            .environment(library.kgCurationService)
            .environment(library.savedSearchServiceGenerated)
            .environment(library.bookmarkServiceGenerated)
            .environment(library.searchService)
            .environment(library.conversationServiceGenerated)
            .environment(library.chatServiceGenerated)
            .environment(library.workspaceStore)
            .environment(library.batchStore)
            .environment(library.workflowServiceGenerated)
            .environment(library.workflowStreamService)
            .environment(library.importService)
            .environment(library.documentServiceGenerated)
            .environment(library.storageService)
            .environment(library.providerService)
            .environment(library.modelService)
            .environment(library.researchService)
            .environment(library.apiClient)
            .environment(libraryManager)
            .environment(claimFocusState)
            .environment(windowState)
            .environment(kgFocusState)
            .environment(library.documentStore)
            .environment(library.entityStore)
            .environment(library.claimStore)
            .environment(library.noteStore)
            .environment(library.annotationStore)
            .environment(library.actionStore)
            .environment(library.auditStore)
            .environment(library.researchStore)
            .environment(library.searchStore)
            .environment(library.artifactStore)
            .environment(library.citationStore)
            .environment(library.referenceStore)
            .environment(library.interpretationStore)
            .environment(library.changeStream)
    }
}
