#if canImport(AppKit)
import AppKit
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "InteractionProfile")

/// Live window resize timing: one log line per drag of a window edge, saying how many frames it
/// drew and how long the average and the slowest frame took, so "resizing is slow" can be read
/// from the log like a slow click (`InteractionProfile`).
///
/// A frame is the gap between two `didResize` notifications during a live resize: AppKit posts
/// one per size it lays out and draws, so a slow layout or SwiftUI update shows as a long gap.
@MainActor
enum ResizeProfile {
    private static var frames: [ObjectIdentifier: [UInt64]] = [:]
    private static var observers: [NSObjectProtocol] = []

    /// Start listening for every window's live resize. Called once, at launch.
    static func install() {
        guard observers.isEmpty else { return }
        let center = NotificationCenter.default
        observers = [
            center.addObserver(forName: NSWindow.willStartLiveResizeNotification, object: nil, queue: .main) { note in
                let key = note.object.map { ObjectIdentifier($0 as AnyObject) }
                MainActor.assumeIsolated { if let key { frames[key] = [DispatchTime.now().uptimeNanoseconds] } }
            },
            center.addObserver(forName: NSWindow.didResizeNotification, object: nil, queue: .main) { note in
                let key = note.object.map { ObjectIdentifier($0 as AnyObject) }
                MainActor.assumeIsolated {
                    guard let key, frames[key] != nil else { return }
                    frames[key]?.append(DispatchTime.now().uptimeNanoseconds)
                }
            },
            center.addObserver(forName: NSWindow.didEndLiveResizeNotification, object: nil, queue: .main) { note in
                let key = note.object.map { ObjectIdentifier($0 as AnyObject) }
                MainActor.assumeIsolated {
                    guard let key, var stamps = frames.removeValue(forKey: key) else { return }
                    stamps.append(DispatchTime.now().uptimeNanoseconds)
                    guard let line = summary(stamps) else { return }
                    logger.info("⏱ window live resize \(line, privacy: .public)")
                }
            }
        ]
    }

    /// "took 1840.0ms: 46 frames, average 40.0ms, slowest 310.5ms" from the start stamp, one stamp
    /// per frame and the end stamp; nil when there is no frame between start and end.
    nonisolated static func summary(_ stamps: [UInt64]) -> String? {
        guard stamps.count >= 3, let first = stamps.first, let last = stamps.last else { return nil }
        let gaps = zip(stamps.dropFirst(), stamps).map { Double($0 &- $1) / 1_000_000 }
        let frameCount = stamps.count - 2
        let totalMs = Double(last &- first) / 1_000_000
        let average = gaps.reduce(0, +) / Double(gaps.count)
        let slowest = gaps.max() ?? 0
        return String(
            format: "took %.1fms: %d frames, average %.1fms, slowest %.1fms",
            totalMs, frameCount, average, slowest
        )
    }
}
#endif
