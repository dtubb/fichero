// The canvas and the Inspector's Edits facet each own an ImageEditorModel over
// the SAME document. Neither could see the other's work, so a rotate from the
// canvas toolbar left the step list empty and an Add Step from the Inspector
// left the canvas showing the pre-edit pixels (Daniel, 2026-09-03: "image
// steps not really showing the steps").
//
// The shared signal is `StorageService.imageEpoch(for:)` — the same counter
// `LibraryImageView` reads — bumped by every successful edit.

@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

#if os(iOS)
import UIKit
#endif

@MainActor
struct ImageEditChainSyncTests {
    private func dummyPreview() -> PreviewImage {
        #if os(macOS)
        let image = PlatformImage()
        #else
        let image = UIImage(systemName: "photo") ?? UIImage()
        #endif
        return PreviewImage(image: image, pixelSize: CGSize(width: 120, height: 80))
    }

    private func source(_ relative: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relative), encoding: .utf8)
    }

    // MARK: - The model's half

    @Test("an unchanged epoch re-fetches nothing")
    func sameEpochIsANoOp() async {
        var calls: [Bool] = []
        let model = ImageEditorModel(documentId: "doc") { _, applyEdits, _ in
            calls.append(applyEdits)
            return self.dummyPreview()
        }

        await model.syncIfExternallyEdited(epoch: 0)

        #expect(calls.isEmpty)
        #expect(model.seenEpoch == 0)
    }

    @Test("a bumped epoch re-renders the edited preview exactly once")
    func bumpedEpochReloadsOnce() async {
        var calls: [Bool] = []
        let model = ImageEditorModel(documentId: "doc") { _, applyEdits, _ in
            calls.append(applyEdits)
            return self.dummyPreview()
        }

        // The source bytes are already in hand; only the render changes.
        model.originalPreview = dummyPreview()

        await model.syncIfExternallyEdited(epoch: 1)
        #expect(calls == [true], "only the EDITED render is re-fetched")
        #expect(model.seenEpoch == 1)

        // Re-delivering the same epoch (SwiftUI can re-evaluate) must not refetch.
        await model.syncIfExternallyEdited(epoch: 1)
        #expect(calls == [true])
    }

    @Test("a model with no document ignores epoch traffic")
    func emptyDocumentIsIgnored() async {
        var calls: [Bool] = []
        let model = ImageEditorModel { _, applyEdits, _ in
            calls.append(applyEdits)
            return self.dummyPreview()
        }

        await model.syncIfExternallyEdited(epoch: 7)

        #expect(calls.isEmpty)
        #expect(model.seenEpoch == 0, "nothing was synced, so nothing is 'seen'")
    }

    @Test("an edit this model made itself does not round-trip back through sync")
    func localEditAccountsForItsOwnBump() throws {
        // rotate() exits early with no service configured, so no bump happens;
        // the invariant under test is the ACCOUNTING, pinned at the source:
        // every path that fires onEditApplied also advances seenEpoch by the
        // one step invalidateImageCache is about to make.
        let text = try source("Views/Preview/ImageEditor/ImageEditorModel.swift")
        #expect(text.contains("private func noteLocalEdit() {"))
        #expect(text.contains("onEditApplied?(documentId)"))
        #expect(text.contains("seenEpoch += 1"))
        // onEditApplied is fired from noteLocalEdit and the sibling arm of the
        // batch loop only — a third bare call site is an unaccounted bump.
        #expect(text.components(separatedBy: "onEditApplied?(").count == 3)
    }

    // MARK: - The hosts' half

    @Test("the Inspector's Edits facet watches the storage epoch")
    func inspectorObservesEpoch() throws {
        let text = try source("Views/Inspector/Document/DocumentInspector+Sections.swift")
        #expect(text.contains(".onChange(of: storageService.imageEpoch(for: document.id))"))
        #expect(text.contains("model.syncIfExternallyEdited(epoch: epoch)"))
        // It seeds from the CURRENT epoch, so opening the facet after an edit
        // does not immediately re-fetch what configure just loaded.
        #expect(text.contains("epoch: storageService.imageEpoch(for: document.id)"))
    }

    @Test("the Edits facet draws the step list, never the pixels")
    func inspectorSkipsPreviewDownloads() throws {
        let text = try source("Views/Inspector/Document/DocumentInspector+Sections.swift")
        #expect(text.contains("loadsPreviews: false"))
        let model = try source("Views/Preview/ImageEditor/ImageEditorModel.swift")
        #expect(model.contains("guard !documentId.isEmpty, loadsPreviews else { return }"))
    }

    @Test("the editor canvas watches the storage epoch for the image it is showing")
    func canvasObservesEpoch() throws {
        let text = try source("Views/Preview/ImageEditor/ImageEditorView.swift")
        // activeDocumentID, not `document.id`: prev/next moves the canvas on
        // without the host's selection necessarily following.
        #expect(text.contains(".onChange(of: storageService.imageEpoch(for: activeDocumentID))"))
        #expect(text.contains("model.syncIfExternallyEdited(epoch: epoch)"))
    }
}
