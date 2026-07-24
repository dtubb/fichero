import XCTest
import Foundation
import OpenAPIRuntime
@testable import FicheroAPIClient

final class BinaryOpenAPIResponseTests: XCTestCase {
    func testImagePreviewBinaryCasesCollectAsData() async throws {
        let pngBytes = Data([0x89, 0x50, 0x4E, 0x47])
        let jpegBytes = Data([0xFF, 0xD8, 0xFF, 0xE0])

        let pngBody = Operations.PreviewImageApiImagesDocumentIdPreviewGet.Output.Ok.Body
            .png(HTTPBody([UInt8](pngBytes)))
        let jpegBody = Operations.PreviewImageApiImagesDocumentIdPreviewGet.Output.Ok.Body
            .jpeg(HTTPBody([UInt8](jpegBytes)))

        let collectedPng = try await Data(collecting: try pngBody.png, upTo: 1024)
        let collectedJpeg = try await Data(collecting: try jpegBody.jpeg, upTo: 1024)

        XCTAssertEqual(collectedPng, pngBytes)
        XCTAssertEqual(collectedJpeg, jpegBytes)
    }

    func testThreadDiagramPngBinaryCaseCollectsAsData() async throws {
        let pngBytes = Data([0x89, 0x50, 0x4E, 0x47])
        let body = Operations.GetThreadDiagramPngApiWorkflowExecutionThreadsThreadIdDiagramPngGet
            .Output.Ok.Body.png(HTTPBody([UInt8](pngBytes)))

        let collectedPng = try await Data(collecting: try body.png, upTo: 1024)

        XCTAssertEqual(collectedPng, pngBytes)
    }
}
