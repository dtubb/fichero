import Foundation
import Observation
import OSLog
import PDFKit

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PDFDocumentCache")

/// Shared per-document PDF cache (#3209). The Preview pane's viewer, loupe, and
/// thumbnails each used to fetch `getSourceData(documentId)` and decode their own
/// `PDFDocument` — so a large scanned PDF was downloaded and parsed up to 3× per
/// session, entirely in memory. This caches, per library, keyed by document id:
///
/// - the fetched source **bytes** — downloaded ONCE and shared by all three
///   (concurrent requests coalesce onto one download); and
/// - the decoded **`PDFDocument`** — parsed ONCE and reused (same instance for
///   repeated requests) by the main-thread viewer.
///
/// Off-main renderers (loupe / thumbnail) take the cached *bytes* and decode a
/// transient document on their own background task: `PDFDocument` is not safe to
/// render off-main while the viewer's `PDFView` renders the same instance on the
/// main thread, so only the bytes are shared with them — the download, the
/// dominant cost, is still deduped.
///
/// Fetches go through an injected closure so the cache stays testable without a
/// live engine and always reads via the storage HTTP endpoint, never a local
/// path. Bounded by a small LRU and evicted on memory pressure.
@MainActor
@Observable
final class PDFDocumentCache {
    /// Fetch raw PDF bytes for a document (via the storage HTTP endpoint).
    typealias Fetch = @MainActor (_ documentId: String) async throws -> Data

    private let fetch: Fetch
    private let maxEntries: Int

    private var dataByID: [String: Data] = [:]
    private var documentByID: [String: PDFDocument] = [:]
    /// Least-recently-used order (front = oldest). A couple of large PDFs is the
    /// realistic working set — anything older evicts on the next access.
    private var lru: [String] = []
    /// In-flight downloads, so N concurrent consumers of the same doc share ONE.
    private var inflight: [String: Task<Data, Error>] = [:]

    @ObservationIgnored private var memoryPressureSource: DispatchSourceMemoryPressure?

    init(maxEntries: Int = 2, fetch: @escaping Fetch) {
        self.maxEntries = maxEntries
        self.fetch = fetch
        installMemoryPressureEviction()
    }

    /// Source bytes for `documentId`, downloaded ONCE and cached. Concurrent
    /// callers for the same id await the single in-flight download.
    func data(for documentId: String) async throws -> Data {
        if let cached = dataByID[documentId] {
            touch(documentId)
            return cached
        }
        if let existing = inflight[documentId] {
            return try await existing.value
        }
        let task = Task { try await fetch(documentId) }
        inflight[documentId] = task
        defer { inflight[documentId] = nil }
        let data = try await task.value
        dataByID[documentId] = data
        touch(documentId)
        evictIfNeeded()
        return data
    }

    /// The decoded `PDFDocument` for `documentId`, parsed ONCE and reused — the
    /// SAME instance on repeated requests. For the main-thread viewer; off-main
    /// renderers use ``data(for:)`` and decode their own transient document.
    func document(for documentId: String) async throws -> PDFDocument? {
        if let cached = documentByID[documentId] {
            touch(documentId)
            return cached
        }
        let data = try await data(for: documentId)
        guard let document = PDFDocument(data: data) else { return nil }
        documentByID[documentId] = document
        touch(documentId)
        evictIfNeeded()
        return document
    }

    /// Drop a single document (e.g. it changed on disk / was closed).
    func evict(_ documentId: String) {
        dataByID[documentId] = nil
        documentByID[documentId] = nil
        lru.removeAll { $0 == documentId }
    }

    /// Drop everything (memory pressure).
    func evictAll() {
        dataByID.removeAll()
        documentByID.removeAll()
        lru.removeAll()
    }

    // MARK: - LRU

    private func touch(_ documentId: String) {
        lru.removeAll { $0 == documentId }
        lru.append(documentId)
    }

    private func evictIfNeeded() {
        while lru.count > maxEntries {
            let victim = lru.removeFirst()
            dataByID[victim] = nil
            documentByID[victim] = nil
        }
    }

    // MARK: - Memory pressure

    private func installMemoryPressureEviction() {
        let source = DispatchSource.makeMemoryPressureSource(eventMask: [.warning, .critical], queue: .main)
        source.setEventHandler { [weak self] in
            Task { @MainActor in
                logger.info("memory pressure — evicting cached PDFs")
                self?.evictAll()
            }
        }
        source.resume()
        memoryPressureSource = source
    }
}
