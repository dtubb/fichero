#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

/// Non-destructive image-editing surface (#469).
///
/// Renders the backend-rendered preview (so the original↔edited toggle is just
/// `apply_edits=false|true` on `/images/{id}/preview`), exposes the edit-chain
/// operations as controls.
///
/// Mounted from `EditorView` for `fileType == .image` documents. Prev/next
/// navigation (#1265) and rubber-band crop/batch (#1265) layer on top in
/// follow-up commits.
struct ImageEditorView: View {
    let document: Document
    /// Optional hook so the host can sync app selection when the user steps to
    /// a sibling image, keeping the window-level inspector pointed at the same
    /// document (#1265). When nil, navigation is still handled internally.
    var onNavigate: ((String) -> Void)?
    /// Multi-file selection (image document ids) for batch-apply (#1265).
    var selectedDocumentIDs: Set<String> = []

    @Environment(APIClient.self) var apiClient
    @Environment(StorageService.self) var storageService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @State var model = ImageEditorModel()

    /// Document currently loaded in the editor. Seeded from `document` and
    /// updated by prev/next so the canvas follows even when the host doesn't
    /// wire `onNavigate`.
    @State var activeDocumentID: String = ""

    // Enhance popover state (sliders default to "no change" = 1.0).
    @State var brightness: Double = 1.0
    @State var contrast: Double = 1.0
    @State var sharpen: Double = 1.0
    @State var showEnhancePopover = false
    /// True once Apply/Auto-Levels kicked off a commit, so dismissing the popover
    /// doesn't discard the live frame the server render is about to replace (#3673).
    @State var enhanceCommitted = false

    // Rotate-angle popover state (#3673) — a fine straighten/rotate slider,
    // live-previewed client-side, committed via the server rotate op.
    @State var rotateAngle: Double = 0
    @State var showRotatePopover = false
    @State var rotateCommitted = false

    /// Marquee selection in normalized image space (0…1); nil when none (#1265).
    @State var marqueeSelection: CGRect?
    @State var compareMode: CompareMode = .single
    @State var compareSplit: CGFloat = 0.5

    @Environment(AnnotationStore.self) var annotationStore

    /// Editable docs in the current multi-selection (for batch-apply).
    var selectedEditableDocs: [Document] {
        siblingEditableDocs.filter { selectedDocumentIDs.contains($0.id) }
    }

    /// Sibling editable docs in the current folder, in display order —
    /// the prev/next set for image files and PDF pages.
    var siblingEditableDocs: [Document] {
        documentStore.currentDocuments.filter { $0.fileType == .image || $0.docType == .page }
    }

    /// The document the editor is actually showing (resolved from the active id).
    var activeDocument: Document {
        siblingEditableDocs.first(where: { $0.id == activeDocumentID })
            ?? documentStore.currentDocuments.first(where: { $0.id == activeDocumentID })
            ?? document
    }

    var currentIndex: Int? {
        siblingEditableDocs.firstIndex(where: { $0.id == activeDocument.id })
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            canvas
        }
        .task(id: document.id) {
            // External selection changed (host drove a new document).
            activeDocumentID = document.id
            marqueeSelection = nil
            await model.configure(
                apiClient: apiClient,
                documentId: document.id,
                page: currentPage(for: document)
            )
            // Invalidate the storage-display cache after every successful edit so
            // StorageDisplayImageCanvas re-fetches edited bytes when exiting edit
            // mode (#2459 / #2469).
            model.onEditApplied = { [storageService] id in
                storageService.invalidateImageCache(for: id)
            }
        }
        .onChange(of: model.chain.operations.count) { _, _ in
            // An op changed the rendered image — a stale region would mismap.
            marqueeSelection = nil
        }
        .alert(
            "Image edit failed",
            isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }
}
