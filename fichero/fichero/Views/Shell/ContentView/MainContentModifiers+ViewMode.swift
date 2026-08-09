import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentViewModifiers")

// Split from ContentViewModifiers.swift (file_length ratchet, 2026-08-09):
// the view-mode routing is the largest single concern in that file and the
// one that keeps growing rulings (#156 single-leaf scope, #161 root set).
extension MainContentModifiers {
    func handleViewModeChange(_ newMode: AppViewMode) {
        logger.info("handleViewModeChange called with mode: \(String(describing: newMode))")

        // Load workflow from API when workflow mode changes
        if case .workflow(let workflowItem) = newMode, let item = workflowItem {
            // Keep editable metadata aligned immediately to avoid rename races while
            // the full workflow payload is loading asynchronously.
            if editingWorkflow.id == item.id {
                editingWorkflow.name = item.name
                editingWorkflow.description = item.description ?? ""
            }

            Task {
                do {
                    let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                    // Use the initializer that copies ALL fields (nodes, edges, provider, model, etc.)
                    editingWorkflow = Workflow(from: fullWorkflow)
                    // Freshly loaded from the server → this IS the baseline for
                    // cross-window re-sync (#2278): no local edits yet.
                    lastSyncedWorkflow = editingWorkflow
                } catch {
                    logger.error("Failed to load workflow: \(error.localizedDescription)")
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                    lastSyncedWorkflow = nil
                }
            }
        }

        // Load children from backend when a library container is selected.
        // Containers = folders (contents) + PDFs (pages, per #568/#570). Using
        // Document.isNavigableContainer keeps this check in sync with
        // double-click routing and sidebar-filter semantics — one property,
        // one definition of "container." Everything else (plain files) shows
        // as a single item in the gallery.
        if case .library(let doc) = newMode, let document = doc {
            guard !isSidebarMultiSelect() else {
                logger.info("Sidebar multi-selection active — the scope handler owns the library set")
                return
            }
            handleLibraryDocumentSelection(document)
        } else if case .library(nil) = newMode {
            handleLibraryRootSelection()
        }
    }

    /// The routed `.library(document)` half of `handleViewModeChange`, split
    /// for the complexity/body ratchets (2026-08-09).
    private func handleLibraryDocumentSelection(_ document: Document) {
            if document.isNavigableContainer {
                logger.info("Loading children for container: \(document.name) (id: \(document.id))")
                selectionLoadTask?.cancel()
                selectionLoadTask = Task {
                    await documentStore.selectCollection(document)
                    guard !Task.isCancelled else { return }
                    detailDocument = document
                    let docCount = documentStore.currentDocuments.count
                    logger.info("selectCollection completed. currentDocuments count: \(docCount)")
                }
            } else {
                // A sidebar PAGE click must drive the PDF canvas to THAT page
                // (Daniel, 2026-08-08: "the preview for it shows the first
                // page"). Same seam as reader scroll/click (#1463): move the
                // page-focus cursor; re-root detailDocument only when the
                // page belongs to a DIFFERENT document than the one on canvas.
                //
                // And for a page, DON'T stomp currentDocuments (Daniel,
                // 2026-08-09 morning: "if I change page in a sidebar, it
                // reloads the PDF and resets to first page"): replacing the
                // loaded sibling set with [page] fired the whole
                // currentDocuments-change cascade — detail re-resolution,
                // grid rebuild — which re-rooted the canvas and threw the
                // cursor away. The parent's pages are already the loaded
                // collection; only the cursor moves.
                if document.docType == .page {
                    pageFocusDocument = document
                    if sidebarPageParentPDFId(for: document) != sidebarDetailPDFId(for: detailDocument) {
                        detailDocument = document
                    }
                } else {
                    logger.info("Showing single file in gallery: \(document.name)")
                    // Apply status overrides so failed/processing state
                    // survives navigation to single-file gallery — direct
                    // assignment bypassed the override layer other load paths
                    // use, so the red-X workflow-error icon vanished on
                    // click-away while success checkmarks persisted (#791).
                    documentStore.currentDocuments =
                        documentStore.applyStatusOverrides([document])
                }
            }
    }

    /// Selecting a LIBRARY header shows its top-level children, like a folder
    /// (Daniel #161, 2026-08-09: 'when global library is selected view should
    /// show children items'). This branch used to log and load NOTHING —
    /// 'No Documents' over a full library.
    private func handleLibraryRootSelection() {
        logger.info("Library mode with no document selected — showing the root set")
        selectionLoadTask?.cancel()
        selectionLoadTask = Task {
            if documentStore.collections.isEmpty {
                await documentStore.loadCollections()
            }
            guard !Task.isCancelled else { return }
            documentStore.currentDocuments =
                documentStore.applyStatusOverrides(documentStore.collections)
        }
    }
}
