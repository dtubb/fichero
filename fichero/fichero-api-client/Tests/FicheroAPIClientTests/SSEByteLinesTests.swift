import XCTest
import OpenAPIRuntime
@testable import FicheroAPIClient

/// The one SSE-frame splitter shared by the change / activity / workflow streams
/// (`SSEByteLines`). Its job is to turn an `HTTPBody` byte stream — whatever
/// transport produced it — into the newline-delimited text lines the services
/// classify, reassembling lines split across chunk boundaries.
final class SSEByteLinesTests: XCTestCase {

    private func collect(_ body: HTTPBody) async throws -> [String] {
        var out: [String] = []
        for try await line in SSEByteLines.lines(from: body) {
            out.append(line)
        }
        return out
    }

    func testSplitsNewlineDelimitedFrames() async throws {
        let body = HTTPBody(Array("data:{\"a\":1}\n\ndata:{\"b\":2}\n".utf8))
        let lines = try await collect(body)
        XCTAssertEqual(lines, ["data:{\"a\":1}", "", "data:{\"b\":2}"])
    }

    func testReassemblesLineSplitAcrossChunks() async throws {
        // Two chunks split a `data:` frame mid-token — the parser must reassemble
        // it into a single line (URLSession.bytes.lines did this for free; the
        // transport hands us raw byte chunks, so the splitter must).
        let chunks: [HTTPBody.ByteChunk] = [
            Array("data:{\"hel".utf8)[...],
            Array("lo\":true}\n".utf8)[...]
        ]
        let stream = AsyncStream<HTTPBody.ByteChunk> { continuation in
            for chunk in chunks { continuation.yield(chunk) }
            continuation.finish()
        }
        let body = HTTPBody(stream, length: .unknown)
        let lines = try await collect(body)
        XCTAssertEqual(lines, ["data:{\"hello\":true}"])
    }

    func testStripsTrailingCarriageReturn() async throws {
        let body = HTTPBody(Array("event: ping\r\ndata:{}\r\n".utf8))
        let lines = try await collect(body)
        XCTAssertEqual(lines, ["event: ping", "data:{}"])
    }

    func testFlushesFinalUnterminatedLine() async throws {
        let body = HTTPBody(Array("data:{\"x\":1}".utf8))
        let lines = try await collect(body)
        XCTAssertEqual(lines, ["data:{\"x\":1}"])
    }

    func testEmptyBodyYieldsNoLines() async throws {
        let lines = try await collect(HTTPBody())
        XCTAssertTrue(lines.isEmpty)
    }
}
