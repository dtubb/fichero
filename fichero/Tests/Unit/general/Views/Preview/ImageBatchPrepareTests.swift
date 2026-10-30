//
//  ImageBatchPrepareTests.swift
//  FicheroTests
//
//  SPEC-BEHAVIOR (`prep.check.apply-correction-to-the-folder`, #5382, #6192): the editor offers "Apply to the rest of this
//  folder" for the last correction a person made (a squaring or a turn), in fractions of the frame or degrees, and the
//  requests use the engine's parameter names. Written 2026-10-30, never run (no xcodebuild in the builder lane).
//

@testable import Fichero
import Foundation
import Testing

struct ImageBatchPrepareTests {
    private func operation(_ raw: [String: Any]) -> ImageEditOperation { ImageEditOperation(raw: AnyCodable(raw)) }

    private let quad: [[Double]] = [[0.1, 0.1], [0.9, 0.12], [1, 0.9], [0, 1]]

    @Test func aPersonsSquaringIsTheCorrectionToCopyWithWholeNumbersToo() {
        let ops = [operation(["op": "square", "who": "person", "params": ["quad": quad]])]
        #expect(BatchPrepare.correction(in: ops) == BatchPrepareOperation(kind: "square", quad: quad))
    }

    @Test func aTurnIsCopiedAsDegreesWhetherItIsWholeOrNot() {
        #expect(BatchPrepare.correction(in: [operation(["op": "rotate", "params": ["angle": 90]])])?.angle == 90)
        #expect(BatchPrepare.correction(in: [operation(["op": "rotate", "params": ["angle": 1.5]])])?.angle == 1.5)
    }

    @Test func theLastCorrectionWinsAndARunsRowOrAnEnhanceIsNotOne() {
        let ops = [operation(["op": "rotate", "params": ["angle": 90]]),
                   operation(["op": "square", "who": "run r1", "params": ["quad": quad]]),
                   operation(["op": "enhance", "params": ["brightness": 1.2]])]
        #expect(BatchPrepare.correction(in: ops)?.kind == "rotate")
        #expect(BatchPrepare.correction(in: [operation(["op": "enhance", "params": [:]])]) == nil)
    }

    @Test func aSquareWithoutFourCornersIsNotACorrection() {
        let bad = operation(["op": "square", "who": "person", "params": ["quad": [[0.1, 0.1]]]])
        #expect(BatchPrepare.correction(in: [bad]) == nil)
    }

    @Test func theSheetSaysHowManyPagesItWillChange() {
        let one = BatchPrepare.summary(pages: 1, operation: .init(kind: "rotate", angle: 90))
        #expect(one == "Copies a turn of 90° to 1 other page in this folder.")
        #expect(BatchPrepare.summary(pages: 12, operation: .init(kind: "square", quad: quad)).contains("12 other pages"))
    }

    @Test func theRequestsUseTheActionsParameterNames() throws {
        let request = ImageBatchPrepareRequest(
            folderId: "f1", operation: .init(kind: "square", quad: quad), sourceDocumentId: "d1")
        let body = try #require(try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
        #expect(body["folder_id"] as? String == "f1" && body["source_document_id"] as? String == "d1")
        #expect((body["operation"] as? [String: Any])?["op"] as? String == "square")
        let undo = try #require(try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(ImageUndoBatchPageRequest(documentId: "d2", batchId: "b1"))) as? [String: Any])
        #expect(undo["document_id"] as? String == "d2" && undo["batch_id"] as? String == "b1")
    }
}
