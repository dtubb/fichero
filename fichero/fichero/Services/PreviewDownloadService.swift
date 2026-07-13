import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PreviewDownloadService")

/// Centralized "download a document's source file to a temp path, then hand it
/// to a system viewer" flow (#3207). Transport now goes through the generated
/// OpenAPI client via `StorageServiceGenerated.fetchSourceFile` (#3726) — no raw
/// URLSession, no hand-built URLRequest, so auth / pinning / library-path
/// middleware stay central. This service owns what is left: the Content-Disposition
/// filename rules, the HTTP-status → human message mapping, and the preview-cache
/// file lifecycle.
///
/// The sanitize, status-check, error-message, and filename routines are unchanged
/// from #3206/#3202/#3207 — only the transport beneath them moved.
struct PreviewDownloadService: Sendable {
    struct Request {
        let documentId: String
        /// Name used when the server sends no (safe) Content-Disposition filename.
        let fallbackFileName: String
        /// Document path, for the linked-external-drive hint in the error message.
        let documentPath: String?
    }

    enum Outcome {
        /// The source file, moved into the preview cache and ready for the viewer.
        case success(URL)
        /// A human-readable message for the error UI (never a bare status code).
        case failure(message: String)
    }

    /// The generated-client storage service does the transport (#3726). This
    /// service owns only the preview-cache lifecycle and the filename rules.
    let storage: StorageServiceGenerated

    /// Download the source file to `FicheroPreview/<id>_<name>` and return it,
    /// or a human error message. Any non-2xx surfaces the engine's JSON `detail`
    /// (not the body handed to a viewer); a `/` or `..` in the server filename is
    /// sanitized away before it can touch the cache path.
    func download(_ request: Request) async -> Outcome {
        do {
            let (tempURL, contentDisposition) = try await storage.fetchSourceFile(request.documentId)

            var fileName = request.fallbackFileName
            if let contentDisposition {
                fileName = Self.preferredDownloadFileName(
                    contentDisposition: contentDisposition,
                    fallback: fileName
                )
            }

            let cacheDir = Self.previewCacheDirectory
            try FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
            let destURL = cacheDir.appendingPathComponent("\(request.documentId)_\(fileName)")

            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try FileManager.default.moveItem(at: tempURL, to: destURL)

            logger.info("Downloaded to: \(destURL.path) (extension: \(destURL.pathExtension))")
            return .success(destURL)
        } catch let error as SourceFileTransportError {
            // A non-2xx body is the engine's JSON error, not the document (#3206):
            // surface its `detail` rather than handing an error page to the viewer.
            return .failure(message: Self.downloadErrorMessage(
                statusCode: error.statusCode,
                body: error.body,
                documentPath: request.documentPath
            ))
        } catch {
            logger.error("Download error: \(error.localizedDescription)")
            return .failure(message: "Failed to load: \(error.localizedDescription)")
        }
    }

    /// Remove a previously-downloaded preview file, guarded to the preview root
    /// so a stray URL can never delete outside the cache.
    func removePreviewFile(_ fileURL: URL?) {
        guard let fileURL else { return }
        let previewRoot = Self.previewCacheDirectory.standardizedFileURL
        let candidate = fileURL.standardizedFileURL
        guard candidate.path.hasPrefix(previewRoot.path) else { return }
        try? FileManager.default.removeItem(at: candidate)
    }

    /// The single temp directory previews are cached in.
    static var previewCacheDirectory: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("FicheroPreview")
    }

    // MARK: - Pure helpers (moved from QuickLookDownloadView; unit-tested)

    /// Human message for a non-2xx source download (#3206): the engine's JSON
    /// `detail` when present (get_source_file returns proper 404 detail), else a
    /// status-coded fallback, plus the linked-external-drive hint that helps a
    /// user mount an unplugged volume. Pure + static so it is unit-testable.
    static func downloadErrorMessage(statusCode: Int, body: Data?, documentPath: String?) -> String {
        var message = "Preview unavailable (HTTP \(statusCode))"
        if let body,
           let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
           let detail = object["detail"] as? String, !detail.isEmpty {
            message = detail
        }
        if let documentPath, documentPath.hasPrefix("/Volumes/") {
            message += "\n\nThis file is linked to an external drive:\n\(documentPath)"
            message += "\n\nMount the drive to view the full resolution file."
        }
        return message
    }

    /// Reduce a server-supplied Content-Disposition filename to a safe leaf
    /// before it is spliced into a cache path (#3207): keep only the last path
    /// component, drop path separators + control chars, reject empty / `.` /
    /// `..`, and cap the length. Returns "" when nothing safe remains (the
    /// caller then keeps its document-derived name). Pure + static → testable.
    static func sanitizedFileName(_ raw: String) -> String {
        // Normalize Windows separators so lastPathComponent (splits on "/" only)
        // reduces "..\\..\\x" to its leaf too, then drop any residual separator +
        // control chars.
        let leaf = (raw.replacingOccurrences(of: "\\", with: "/") as NSString).lastPathComponent
        let kept = leaf.unicodeScalars.filter { scalar in
            scalar != "/" && !CharacterSet.controlCharacters.contains(scalar)
        }
        let cleaned = String(String.UnicodeScalarView(kept)).trimmingCharacters(in: .whitespaces)
        guard !cleaned.isEmpty, cleaned != ".", cleaned != ".." else { return "" }
        return String(cleaned.prefix(200))
    }

    /// Pick the best cache filename from a Content-Disposition header. Supports
    /// both RFC 5987 `filename*=` (UTF-8 percent-encoded) and plain
    /// `filename=`. Every server-provided value is sanitized before use; if no
    /// safe value remains, the caller's fallback is kept. Pure + static so the
    /// Unicode/header parsing contract is unit-testable.
    static func preferredDownloadFileName(contentDisposition: String, fallback: String) -> String {
        let parts = contentDisposition.split(separator: ";").map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        for part in parts {
            guard part.lowercased().hasPrefix("filename*=") else { continue }
            let rawValue = String(part.dropFirst("filename*=".count))
                .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            let encoded = rawValue.components(separatedBy: "''").last ?? rawValue
            if let decoded = encoded.removingPercentEncoding {
                let sanitized = sanitizedFileName(decoded)
                if !sanitized.isEmpty { return sanitized }
            }
        }

        for part in parts {
            guard part.lowercased().hasPrefix("filename=") else { continue }
            let rawValue = String(part.dropFirst("filename=".count))
                .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            let sanitized = sanitizedFileName(rawValue)
            if !sanitized.isEmpty { return sanitized }
        }

        return fallback
    }
}
