import AVFoundation
import FicheroAPIClient
import Foundation
import OSLog
import os
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
/// mutable state (`bufferedData`, `fetchTask`) is guarded by the `state` lock.
final class StorageResourceAVAssetDelegate: NSObject, AVAssetResourceLoaderDelegate, @unchecked Sendable {
    /// The UTI reported to AVFoundation for the media container, derived from the
    /// document's file extension by the caller.
    private let contentTypeUTI: String?

    /// Buffer + in-flight fetch, guarded by an async-safe unfair lock (NSLock's
    /// `lock()`/`unlock()` are unavailable from async contexts under Swift 6).
    private struct BufferState {
        var bufferedData: Data?
        var fetchTask: Task<Data, Error>?
    }
    private let state = OSAllocatedUnfairLock(initialState: BufferState())

    private enum FetchOutcome {
        case ready(Data)
        case awaiting(Task<Data, Error>)
    }

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
                let data = try await self.bufferedData(for: url)
                self.fulfil(transfer.value, with: data)
            } catch {
                logger.error("fichero-res media load failed for \(url.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)")
                transfer.value.finishLoading(with: error)
            }
        }
        return true
    }

    /// Fetch (once) and buffer the full source bytes for `url`.
    private func bufferedData(for url: URL) async throws -> Data {
        // Decide under the lock: serve the buffer, join the in-flight fetch, or
        // start one (created + stored atomically so two callers can't both fetch).
        let outcome: FetchOutcome = state.withLock { current in
            if let bufferedData = current.bufferedData {
                return .ready(bufferedData)
            }
            if let fetchTask = current.fetchTask {
                return .awaiting(fetchTask)
            }
            let task = Task { () throws -> Data in
                let resource = try await Self.load(url: url)
                return resource.data
            }
            current.fetchTask = task
            return .awaiting(task)
        }

        switch outcome {
        case .ready(let bufferedData):
            return bufferedData
        case .awaiting(let task):
            let data = try await task.value
            state.withLock { $0.bufferedData = data }
            return data
        }
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
