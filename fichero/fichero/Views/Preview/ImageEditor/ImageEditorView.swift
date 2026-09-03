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
    /// Leave edit mode (Daniel, 2026-08-30: "when you are done editing an
    /// image, how do you get out?"). Edits are already committed per Apply —
    /// Done only flips the facet back; nil hides the button.
    var onDone: (() -> Void)?

    @Environment(APIClient.self) var apiClient
    @Environment(StorageService.self) var storageService
    /// Optional, like the display canvas's own: a host without a rendition
    /// service simply has no rendition caches to drop.
    @Environment(RenditionService.self) var renditionService: RenditionService?
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
    /// Canvas zoom for the COMPARE modes (Daniel, 2026-09-01: the editor had
    /// no way to get closer to what it was changing). Single mode is a
    /// `DocumentCanvas`, which floats the shared zoom pill over itself and
    /// owns its own scale — a second zoom there would be two controls fighting
    /// over one image. Side-by-side and wipe are plain `Image`s with no scale
    /// of their own, and this is it.
    @State var compareZoom: CGFloat = 1.0
    /// Width of the edit-steps stack beside the canvas. Matches the window
    /// Inspector's own column so the two lists read as the same object in two
    /// places rather than two different panels.
    // stepsPanelWidth removed 2026-09-02 with the beside-canvas steps copy —
    // the Inspector's Edits facet is the one steps list.
    static let minCompareZoom: CGFloat = 0.25
    static let maxCompareZoom: CGFloat = 8.0
    /// Revert to Original confirmation — every step is already committed, so
    /// reverting always discards saved work and always asks (Daniel, 2026-08-31).
    @State var showRevertConfirm = false
    /// Paste Edits across a multi-selection replaces saved chains on files
    /// that may not be on screen, so it asks first (Daniel, 2026-09-02).
    @State var showPasteManyConfirm = false

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
            // ONE steps list, in the window Inspector's Edits facet — which
            // auto-opens with edit mode and now edits steps in place too
            // (Daniel, 2026-09-02: the beside-canvas copy duplicated the
            // Inspector's panel one divider apart; see his 9:50pm screenshot).
            canvas
        }
        // ⌘A over a shown image selects the WHOLE image (Daniel, 2026-08-23).
        // The marquee already speaks normalized image space, so "everything"
        // is the unit rect — no new selection concept, just its full extent.
        // Published rather than key-handled here: `SelectAllButton` owns the
        // chord and asks which pane has focus.
        .focusedSceneValue(
            \.previewSelectAll,
            FocusedLibraryAction(
                isEnabled: model.preview != nil,
                run: { marqueeSelection = CGRect(x: 0, y: 0, width: 1, height: 1) }
            )
        )
        // ⌘Z while editing an image undoes the last committed edit step
        // (Daniel, 2026-08-31). Published on its own key so the Edit menu's
        // `UndoLastActionButton` routes here ahead of navigation-back — a bare
        // `.keyboardShortcut` on the toolbar button loses to the menu's key
        // equivalent on macOS.
        .focusedSceneValue(
            \.imageEditUndoAction,
            FocusedLibraryAction(
                isEnabled: !model.chain.isEmpty && !model.isBusy,
                run: { Task { await model.undoLastStep() } }
            )
        )
        .task(id: document.id) {
            // External selection changed (host drove a new document).
            activeDocumentID = document.id
            marqueeSelection = nil
            await model.configure(
                apiClient: apiClient,
                documentId: document.id,
                page: currentPage(for: document)
            )
            // Invalidate every derived-pixel cache after each successful edit,
            // not just on the way out.
            //
            // Storage covers the thumbnail / display / source blobs (#2459 /
            // #2469). Renditions are a SECOND cache the display canvas
            // consults FIRST — a list plus per-rendition bytes keyed by ids
            // that editing rewrites in place — so leaving them warm is why a
            // rotate showed a stale picture in the library row and the preview
            // strip while the editor was still open (Daniel, 2026-09-02).
            // `finishEditing` drops both again on Done; doing it here as well
            // is what makes the rest of the window agree with the canvas
            // BEFORE you leave the editor.
            model.onEditApplied = { [storageService, renditionService] id in
                storageService.invalidateImageCache(for: id)
                renditionService?.invalidate(documentId: id)
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
