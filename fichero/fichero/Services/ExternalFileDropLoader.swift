import Foundation
import OSLog
import UniformTypeIdentifiers

let externalDropLoaderLogger = Logger(subsystem: "app.fichero.fichero", category: "ExternalFileDropLoader")

/// Loads a file URL from an `NSItemProvider` using whichever API the
/// provider actually supports (#4184).
///
/// Extracted from `SidebarItemRow+DropHandlers.swift` (#587's fix) so every
/// external-drop surface shares ONE loader — the sidebar row drop target
/// AND the root content-pane drop target (#4184) — instead of the content
/// pane quietly using a weaker path nobody had reason to notice.
///
/// Finder drags advertise `public.file-url` and respond to
/// `loadObject(URL.self)` directly — the cheap, common case, and the ONLY
/// case SwiftUI's `Transferable`-based `.dropDestination(for: URL.self)`
/// handles, because `URL: Transferable` decodes via that same file-url
/// promise. Drags from Mail attachments, Safari image/PDF drags, and
/// in-progress Downloads items often advertise only a CONTENT type
/// (`public.jpeg`, `com.adobe.pdf`) with no file-url promise attached —
/// `loadObject(URL.self)` returns nil for these, and so does `Transferable`.
/// `loadFileRepresentation(forTypeIdentifier:)` against the provider's own
/// advertised UTI is the fallback that actually reads them. This is the
/// promise-type asymmetry behind "drag-and-drop of a PDF doesn't work from
/// some locations" — it was never about the drop TARGET.
enum ExternalFileDropLoader {
    /// Returns the URL (copied into a stable location if the provider
    /// supplied a temp path) or throws if no representation yields
    /// anything readable.
    static func loadAnyFileURL(from provider: NSItemProvider) async throws -> URL {
        let utis = provider.registeredTypeIdentifiers
        let canURL = provider.canLoadObject(ofClass: URL.self)
        externalDropLoaderLogger.debug("loadAnyFileURL: canLoadURL=\(canURL) UTIs=[\(utis.joined(separator: ", "))]")

        // Cheapest path first: direct URL load if the provider advertises it.
        if canURL {
            externalDropLoaderLogger.debug("  → trying direct URL load (canLoadObject=true)")
            do {
                let url = try await loadURL(from: provider)
                externalDropLoaderLogger.debug("  direct URL load succeeded: \(url.lastPathComponent) [\(url.pathExtension)]")
                return url
            } catch {
                externalDropLoaderLogger.warning(
                    "  direct URL load failed despite canLoadObject=true: \(error.localizedDescription)"
                )
                // Fall through to representation-based fallback rather than throwing,
                // in case the provider lied about canLoadObject (seen with some .mov drags).
            }
        }

        // Otherwise iterate the provider's registered UTIs and ask each
        // for a file representation until one produces a URL. This is the
        // case for drags advertising only a content UTI like `public.jpeg`
        // or `com.adobe.pdf` — they don't respond to `loadObject(URL.self)`
        // but do respond to `loadFileRepresentation(forTypeIdentifier:)`.
        guard !utis.isEmpty else {
            externalDropLoaderLogger.warning("  provider has no UTIs and canLoadObject=false — no path available")
            throw NSError(
                domain: "ExternalFileDrop",
                code: -1,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Provider advertises neither URL nor any type identifiers"
                ]
            )
        }
        externalDropLoaderLogger.debug("  → trying loadFileRepresentation fallback for \(utis.count) UTI(s)")
        for identifier in utis {
            externalDropLoaderLogger.debug("    trying UTI: \(identifier)")
            if let url = try? await loadFileRepresentation(
                from: provider,
                typeIdentifier: identifier
            ) {
                externalDropLoaderLogger.debug("    representation succeeded for UTI \(identifier): \(url.lastPathComponent)")
                return url
            } else {
                externalDropLoaderLogger.debug("    representation failed for UTI \(identifier)")
            }
        }
        externalDropLoaderLogger.warning(
            "  all \(utis.count) UTI representation(s) failed; UTIs=[\(utis.joined(separator: ", "))]"
        )
        throw NSError(
            domain: "ExternalFileDrop",
            code: -1,
            userInfo: [
                NSLocalizedDescriptionKey:
                    "No representation yielded a file URL; advertised UTIs: \(utis)"
            ]
        )
    }

    /// Wraps `NSItemProvider.loadFileRepresentation(forTypeIdentifier:
    /// completionHandler:)` as async/throws. The provider hands us a
    /// temporary file URL valid only until the completion returns, so
    /// we copy the file to a stable `fichero-drop-<uuid>` temp directory
    /// before resolving — otherwise the import pipeline would race
    /// against the temp file being deleted. Callers should remove that
    /// directory once the import using it has completed (see
    /// `sidebarTemporaryDropDirectories` for the matching filter).
    static func loadFileRepresentation(
        from provider: NSItemProvider,
        typeIdentifier: String
    ) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadFileRepresentation(
                forTypeIdentifier: typeIdentifier
            ) { temporaryURL, error in
                if let error {
                    externalDropLoaderLogger.debug(
                        "      loadFileRepresentation(\(typeIdentifier)) callback error: \(error.localizedDescription)"
                    )
                    continuation.resume(throwing: error)
                    return
                }
                guard let temporaryURL else {
                    externalDropLoaderLogger.debug(
                        "      loadFileRepresentation(\(typeIdentifier)) callback: nil URL, no error"
                    )
                    continuation.resume(throwing: NSError(
                        domain: "ExternalFileDrop",
                        code: -2,
                        userInfo: [NSLocalizedDescriptionKey: "Empty URL from loadFileRepresentation"]
                    ))
                    return
                }
                externalDropLoaderLogger.debug("      loadFileRepresentation(\(typeIdentifier)) temp URL: \(temporaryURL.path)")
                // Copy to a stable caches path — the temporaryURL is
                // deleted as soon as this closure returns.
                let destinationDir = FileManager.default.temporaryDirectory
                    .appendingPathComponent("fichero-drop-\(UUID().uuidString)")
                do {
                    try FileManager.default.createDirectory(at: destinationDir, withIntermediateDirectories: true)
                    let destination = destinationDir.appendingPathComponent(temporaryURL.lastPathComponent)
                    try FileManager.default.copyItem(at: temporaryURL, to: destination)
                    externalDropLoaderLogger.debug("      copied to stable path: \(destination.path)")
                    continuation.resume(returning: destination)
                } catch {
                    externalDropLoaderLogger.debug("      copy to stable path failed: \(error.localizedDescription)")
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    static func loadURL(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    externalDropLoaderLogger.debug("      loadObject(URL) error: \(error.localizedDescription)")
                    continuation.resume(throwing: error)
                } else if let url {
                    externalDropLoaderLogger.debug("      loadObject(URL) → \(url.absoluteString)")
                    continuation.resume(returning: url)
                } else {
                    externalDropLoaderLogger.debug("      loadObject(URL) → nil URL, no error")
                    continuation.resume(throwing: NSError(domain: "ExternalFileDrop", code: -1))
                }
            }
        }
    }
}

/// Temp directories `ExternalFileDropLoader.loadFileRepresentation` created
/// among `urls` — the caller removes them once its import finishes with
/// them. Shared filter so every drop surface agrees on the naming
/// convention (`fichero-drop-<uuid>`).
func externalDropTemporaryDirectories(for urls: [URL]) -> [URL] {
    Array(
        Set(
            urls
                .filter { $0.path.contains("/fichero-drop-") }
                .map { $0.deletingLastPathComponent() }
        )
    )
}
