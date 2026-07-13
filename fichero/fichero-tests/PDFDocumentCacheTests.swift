@testable import Fichero
import Foundation
import PDFKit
import Testing

/// The shared per-document PDF cache (#3209): download once, decode once, reuse.
@MainActor
@Suite("PDFDocumentCache")
struct PDFDocumentCacheTests {

    /// A minimal one-page PDF as raw bytes, so tests decode a real PDFDocument.
    private static func onePagePDFData() -> Data {
        let bounds = CGRect(x: 0, y: 0, width: 72, height: 72)
        let doc = PDFDocument()
        let page = PDFPage()
        page.setBounds(bounds, for: .mediaBox)
        doc.insert(page, at: 0)
        return doc.dataRepresentation() ?? Data()
    }

    @Test("repeated document(for:) returns the SAME decoded instance")
    func documentIsDecodedOnceAndReused() async throws {
        var fetchCount = 0
        let data = Self.onePagePDFData()
        let cache = PDFDocumentCache { _ in
            fetchCount += 1
            return data
        }

        let first = try await cache.document(for: "doc-1")
        let second = try await cache.document(for: "doc-1")

        #expect(first != nil)
        #expect(first === second, "same PDFDocument instance is reused")
        #expect(fetchCount == 1, "the source bytes are downloaded only once")
    }

    @Test("data(for:) downloads once and is shared by viewer + loupe + thumbnails")
    func dataIsDownloadedOnce() async throws {
        var fetchCount = 0
        let data = Self.onePagePDFData()
        let cache = PDFDocumentCache { _ in
            fetchCount += 1
            return data
        }

        // Simulate the three consumers all asking for the same document's bytes.
        _ = try await cache.data(for: "doc-1")   // viewer
        _ = try await cache.data(for: "doc-1")   // loupe
        _ = try await cache.data(for: "doc-1")   // thumbnail

        #expect(fetchCount == 1, "one download shared by all three consumers")
    }

    @Test("eviction drops the cached instance so it re-fetches")
    func evictionForcesReFetch() async throws {
        var fetchCount = 0
        let data = Self.onePagePDFData()
        let cache = PDFDocumentCache { _ in
            fetchCount += 1
            return data
        }

        _ = try await cache.document(for: "doc-1")
        cache.evictAll()
        _ = try await cache.document(for: "doc-1")

        #expect(fetchCount == 2, "after eviction the document is fetched + decoded again")
    }

    @Test("LRU cap evicts the oldest document once the working set is exceeded")
    func lruEvictsOldest() async throws {
        var fetchCounts: [String: Int] = [:]
        let data = Self.onePagePDFData()
        let cache = PDFDocumentCache(maxEntries: 2) { id in
            fetchCounts[id, default: 0] += 1
            return data
        }

        _ = try await cache.document(for: "a")  // {a}
        _ = try await cache.document(for: "b")  // {a,b}
        _ = try await cache.document(for: "c")  // {b,c} — a evicted
        _ = try await cache.document(for: "a")  // a re-fetched

        #expect(fetchCounts["a"] == 2, "the oldest (a) was evicted and re-fetched")
        #expect(fetchCounts["b"] == 1)
        #expect(fetchCounts["c"] == 1)
    }
}
