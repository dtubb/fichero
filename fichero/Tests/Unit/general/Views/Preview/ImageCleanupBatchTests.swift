//
//  ImageCleanupBatchTests.swift
//  FicheroTests
//
//  SPEC-BEHAVIOR (`image.enhance.batch-preview-undo`, #6192, Step 4.5): a cleanup step applied to a folder opens one sheet
//  that previews three pages, applies once, names each page with Undo and undoes the batch once. Never run (no xcodebuild
//  in the builder lane).
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ImageCleanupBatchTests {
    /// A stub engine that counts what the sheet asks of it.
    @MainActor final class Engine: ImageCleanupBatching {
        var previews = 0, applies = 0, undos: [String] = []
        func preview(folderId: String, step: CleanupStep) async throws -> CleanupPreview {
            previews += 1
            let page = CleanupPreviewPage(id: "p1", name: "Page 1", before: Data([1]), after: Data([2]))
            return CleanupPreview(pages: 12, samples: [page])
        }
        func apply(folderId: String, step: CleanupStep) async throws -> String { applies += 1; return "batch-1" }
        func undo(batchId: String) async throws { undos.append(batchId) }
    }

    private let pages = [CleanupPageRef(id: "p1", name: "Page 1"), CleanupPageRef(id: "p2", name: "Page 2")]

    private func model(_ engine: Engine) -> ImageCleanupBatchModel {
        ImageCleanupBatchModel(folderId: "f", step: CleanupStep.all[0], pages: pages, service: engine)
    }

    @Test func theSheetPreviewsOnceApplysOnceAndUndoesOnce() async {
        let engine = Engine()
        let sheet = model(engine)
        await sheet.loadPreview()
        #expect(sheet.summary == "Auto Enhance on 12 pages in this folder.")
        await sheet.apply()
        #expect(sheet.phase == .applied(batchId: "batch-1"))
        #expect(sheet.appliedPages == pages)
        await sheet.undoAll()
        #expect(sheet.phase == .undone && sheet.appliedPages.isEmpty)
        #expect((engine.previews, engine.applies, engine.undos) == (1, 1, ["batch-1"]))
    }

    @Test func applyWaitsForThePreviewAndAPageUndoLeavesTheOthers() async {
        let engine = Engine()
        let sheet = model(engine)
        await sheet.apply()  // not ready yet: nothing is sent
        #expect(engine.applies == 0)
        await sheet.loadPreview()
        await sheet.apply()
        sheet.pageUndone("p1")
        #expect(sheet.appliedPages.map(\.id) == ["p2"])
    }

    @Test func autoEnhanceIsTheClaheCleanupAndEveryStepNamesAnEngineOperation() {
        let first = CleanupStep.all[0]
        #expect(first.operation == "enhance" && first.params["method"] == "clahe")
        #expect(Set(CleanupStep.all.map(\.id)).count == CleanupStep.all.count)
    }
}
