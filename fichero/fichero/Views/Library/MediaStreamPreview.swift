import AVFoundation
import AVKit
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MediaStreamPreview")

/// Streams an audio/video document via `AVPlayer` against the storage HTTP
/// endpoint (#3208), instead of `QuickLookDownloadView` which downloads the WHOLE
/// file to a temp path before showing anything — minutes of blank pane and
/// gigabytes duplicated for large recordings.
///
/// The player points an `AVURLAsset` at `apiClient.sourceURL(for:)` and carries
/// the SAME auth as every other storage fetch (`Authorization: Bearer` +
/// `X-Fichero-Library-Path`) via `AVURLAssetHTTPHeaderFieldsKey` — the headers
/// stay inside the asset's request options, no bare token in the URL, no local
/// path. AVFoundation then fetches progressively (Range requests) rather than up
/// front. Cross-platform (AVKit on macOS + iOS).
///
/// `canStream(_:)` gates this to formats AVFoundation actually plays; anything
/// else (mkv / avi / …) stays on the QuickLook download fallback.
struct MediaStreamPreview: View {
    let document: Document

    @Environment(APIClient.self) private var apiClient
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
            } else {
                // Brief — only while the player is being constructed; playback
                // itself streams, so this is not the old whole-file download wait.
                ProgressView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .windowBackgroundColor))
        .task(id: document.id) { makePlayer() }
        .onDisappear { player?.pause() }
    }

    private func makePlayer() {
        let url = apiClient.sourceURL(for: document.id)
        // Reuse the exact auth headers every other storage fetch uses, rather
        // than re-deriving them — keeps the token out of the URL and in step
        // with the middleware (#742/#3076).
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: apiClient.currentLibraryPath)
        let headers = request.allHTTPHeaderFields ?? [:]

        // The header-fields option key isn't surfaced as a Swift symbol on this
        // SDK; its stable underlying string value carries the auth headers into
        // AVFoundation's own networking.
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        let item = AVPlayerItem(asset: asset)
        logger.info("Streaming media for document: \(document.id, privacy: .public)")
        player = AVPlayer(playerItem: item)
    }

    // MARK: - Format gating

    /// Whether AVFoundation can stream this document. Containers it can't play
    /// (mkv / avi / wmv / flv / webm / ogg) fall back to the QuickLook download
    /// path so nothing regresses to a broken player.
    static func canStream(_ document: Document) -> Bool {
        streamableExtensions.contains(mediaExtension(for: document))
    }

    private static let streamableExtensions: Set<String> = [
        // Audio AVFoundation plays natively.
        "mp3", "m4a", "aac", "wav", "aif", "aiff", "caf", "au", "m4b",
        // Video AVFoundation plays natively.
        "mp4", "m4v", "mov"
    ]

    /// Extension from the document name (or its path when present) — a *format*
    /// decision, not rendering from a local file path.
    private static func mediaExtension(for document: Document) -> String {
        let source = (document.path?.isEmpty == false) ? document.path! : document.name
        return (source as NSString).pathExtension.lowercased()
    }
}
