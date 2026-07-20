import AVFoundation
import AVKit
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MediaStreamPreview")

/// Streams an audio/video document via `AVPlayer` (#3208), instead of
/// `QuickLookDownloadView` which downloads the WHOLE file to a temp path before
/// showing anything — minutes of blank pane and gigabytes duplicated for large
/// recordings.
///
/// The player points an `AVURLAsset` at a `fichero-res://source/<docId>` URL and
/// drives it through `StorageResourceAVAssetDelegate`, so the media bytes travel
/// the generated OpenAPI client over whatever transport it dials (`.https`,
/// `.uds`, in-memory) — never a hand-built `https://127.0.0.1:8765/...` URL that
/// breaks under UDS/in-memory. Auth + library-path headers are applied centrally
/// by the client middleware, so there is no bare token in the URL and no local
/// path. Cross-platform (AVKit on macOS + iOS).
///
/// Streaming caveat: the generated source op has no `Range` parameter, so the
/// delegate buffers the whole file once and serves seeks from that buffer (see
/// `StorageResourceAVAssetDelegate`). Seeks are instant; first playback waits for
/// the download.
///
/// `canStream(_:)` gates this to formats AVFoundation actually plays; anything
/// else (mkv / avi / …) stays on the QuickLook download fallback.
struct MediaStreamPreview: View {
    let document: Document

    @Environment(APIClient.self) private var apiClient
    @State private var player: AVPlayer?
    /// Retains the resource-loader delegate for the asset's lifetime —
    /// `AVURLAsset.resourceLoader` holds its delegate weakly.
    @State private var resourceDelegate: StorageResourceAVAssetDelegate?

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
        // A `fichero-res://source/<docId>` URL, resolved by the resource-loader
        // delegate through the generated client — transport-agnostic, no raw
        // engine URL, no auth headers to hand-assemble (the client middleware
        // owns auth + library-path centrally).
        let url = apiClient.storageResourceURL(.source, for: document.id)
        let delegate = StorageResourceAVAssetDelegate(fileExtension: Self.mediaExtension(for: document))
        let asset = AVURLAsset(url: url)
        asset.resourceLoader.setDelegate(delegate, queue: DispatchQueue(label: "app.fichero.media-loader"))
        resourceDelegate = delegate
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
