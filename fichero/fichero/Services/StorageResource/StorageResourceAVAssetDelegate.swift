import AVFoundation
import FicheroAPIClient
import Foundation
import OSLog
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageResourceAVAssetDelegate")

/// `AVAssetResourceLoaderDelegate` that feeds an `AVURLAsset` pointed at a
/// `fichero-res://source/<docId>` URL, serving the media bytes through the
/// transport-agnostic `StorageResourceLoader`.
///
/// ## Range / streaming honesty (engine gap)
/// True progressive streaming needs byte-range fetches, but the generated
/// `getSourceFileApiStorageSourceDocIdGet` operation exposes **no** `Range`
/// parameter (the engine's FastAPI `FileResponse` honours HTTP `Range` at the
/// transport level, but that capability isn't in the OpenAPI contract, so the
/// typed client can't request a partial body — and over `.uds`/in-memory there
/// is no raw HTTP request for us to attach a `Range` header to). This delegate
/// therefore fetches the **whole** source once, buffers it, and satisfies every
/// `AVAssetResourceLoadingRequest` — including seeks — by slicing that buffer.
/// Seeking within a played file is instant, but first playback waits for the
/// full download. Restoring progressive streaming requires adding a
/// range-capable storage operation to the OpenAPI surface (engine change) —
/// tracked as the streaming gap for this work.
/// Transfers a non-`Sendable` value across a `Task` boundary. Sound here
/// because AVFoundation hands each `AVAssetResourceLoadingRequest` to exactly
/// one delegate callback, and we service it on a single load `Task` — the value
/// is never touched concurrently.
private struct UncheckedTransfer<Value>: @unchecked Sendable {
    let value: Value
}

/// `@unchecked Sendable`: AVFoundation invokes the delegate on the queue passed
/// to `setDelegate(_:queue:)` and the async fetch runs off that queue. The only
/// mutable state (`bufferedData`, `fetchTask`) is guarded by `lock`.
final class StorageResourceAVAssetDelegate: NSObject, AVAssetResourceLoaderDelegate, @unchecked Sendable {
    /// The UTI reported to AVFoundation for the media container, derived from the
    /// document's file extension by the caller.
    private let contentTypeUTI: String?

    /// Serialises access to the shared buffer / fetch task off the loader queue.
    private let lock = NSLock()
    private var bufferedData: Data?
    private var fetchTask: Task<Data, Error>?

    /// - Parameter fileExtension: the source document's extension (e.g. "mp4"),
    ///   used to derive the container UTI AVFoundation needs to pick a demuxer.
    init(fileExtension: String) {
        self.contentTypeUTI = UTType(filenameExtension: fileExtension.lowercased())?.identifier
    }

    func resourceLoader(
        _ resourceLoader: AVAssetResourceLoader,
        shouldWaitForLoadingOfRequestedResource loadingRequest: AVAssetResourceLoadingRequest
    ) -> Bool {
        guard let url = loadingRequest.request.url else { return false }
        let transfer = UncheckedTransfer(value: loadingRequest)
        Task { [weak self] in
            guard let self else { return }
            do {
                let data = try await self.data(for: url)
                self.fulfil(transfer.value, with: data)
            } catch {
                logger.error("fichero-res media load failed for \(url.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)")
                transfer.value.finishLoading(with: error)
            }
        }
        return true
    }

    /// Fetch (once) and buffer the full source bytes for `url`.
    private func data(for url: URL) async throws -> Data {
        lock.lock()
        if let bufferedData {
            lock.unlock()
            return bufferedData
        }
        if let fetchTask {
            lock.unlock()
            return try await fetchTask.value
        }
        let task = Task { () throws -> Data in
            let resource = try await Self.load(url: url)
            return resource.data
        }
        fetchTask = task
        lock.unlock()

        let data = try await task.value
        lock.lock()
        bufferedData = data
        lock.unlock()
        return data
    }

    @MainActor
    private static func load(url: URL) async throws -> StorageResourceLoader.Resource {
        guard let (loader, parsed) = StorageResourceRegistry.shared.resolve(url) else {
            if let parsed = StorageResourceURL.parse(url) {
                throw StorageResourceError.unknownClient(token: parsed.token)
            }
            throw StorageResourceError.malformedURL(url)
        }
        return try await loader.fetch(kind: parsed.kind, documentId: parsed.documentId)
    }

    /// Answer the content-information and data portions of a loading request from
    /// the buffered bytes.
    private func fulfil(_ loadingRequest: AVAssetResourceLoadingRequest, with data: Data) {
        if let infoRequest = loadingRequest.contentInformationRequest {
            infoRequest.contentType = contentTypeUTI
            infoRequest.contentLength = Int64(data.count)
            // We hold the whole file, so seeks are satisfiable — report range
            // support even though the fetch itself was whole-file.
            infoRequest.isByteRangeAccessSupported = true
        }

        if let dataRequest = loadingRequest.dataRequest {
            let requestedOffset = Int(dataRequest.requestedOffset)
            guard requestedOffset <= data.count else {
                // Out-of-range seek: no bytes to serve, but the request is still
                // "complete" — finish cleanly rather than hang.
                loadingRequest.finishLoading()
                return
            }
            let end: Int
            if dataRequest.requestsAllDataToEndOfResource {
                end = data.count
            } else {
                end = min(requestedOffset + dataRequest.requestedLength, data.count)
            }
            if end > requestedOffset {
                dataRequest.respond(with: data.subdata(in: requestedOffset..<end))
            }
        }

        loadingRequest.finishLoading()
    }
}
