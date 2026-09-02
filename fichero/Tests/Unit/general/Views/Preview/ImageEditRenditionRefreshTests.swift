@testable import Fichero
import Foundation
import Testing

/// After an edit lands, every DERIVED copy of the picture has to be dropped —
/// not just the storage blobs (Daniel, 2026-09-02: rotate an image and the
/// library row and preview strip kept showing the old one).
///
/// Two caches sit between the engine and the screen: `StorageService`'s
/// thumbnail / display / source images, and `RenditionService`'s rendition
/// LIST plus per-rendition bytes — which the display canvas consults FIRST and
/// which are keyed by ids that editing rewrites in place. Clearing one and not
/// the other leaves the stale picture on screen. Pinned against the source
/// because the hook is a closure inside a SwiftUI `.task`.
struct ImageEditRenditionRefreshTests {
    private func editorSource() throws -> String {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageEditor/ImageEditorView.swift"
        )
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("every successful edit drops BOTH derived-pixel caches, not just storage")
    func editAppliedInvalidatesBothCaches() throws {
        let source = try editorSource()
        #expect(source.contains("model.onEditApplied = { [storageService, renditionService] id in"))
        #expect(source.contains("storageService.invalidateImageCache(for: id)"))
        #expect(source.contains("renditionService?.invalidate(documentId: id)"))
    }

    @Test("the way out still drops both, so leaving the editor cannot show stale pixels")
    func doneAlsoInvalidatesBoth() throws {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageEditor/ImageEditorView+Toolbar.swift"
        )
        let toolbar = try String(contentsOf: url, encoding: .utf8)
        #expect(toolbar.contains("private func finishEditing("))
        #expect(toolbar.contains("storageService.invalidateImageCache(for: activeDocumentID)"))
        #expect(toolbar.contains("renditionService?.invalidate(documentId: activeDocumentID)"))
    }

    @Test("batch-applied edits invalidate per document, not only for the active one")
    func batchApplyInvalidatesEveryTarget() throws {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageEditor/ImageEditorModel.swift"
        )
        let model = try String(contentsOf: url, encoding: .utf8)
        // The hook fires with the id that was actually edited, inside the
        // batch loop — an off-screen document's caches are just as stale.
        #expect(model.contains("try await operation(service, id)"))
        #expect(model.contains("onEditApplied?(id)"))
        #expect(model.contains("onEditApplied?(documentId)"))
    }
}
