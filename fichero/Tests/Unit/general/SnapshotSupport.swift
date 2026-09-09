import SwiftUI
import Testing
import UniformTypeIdentifiers

/// Snapshot layer for design-led UX testing (Testing Constitution: the cheap
/// check below XCUITest). Renders a SwiftUI view to a deterministic PNG via
/// `ImageRenderer` — no app launch, no engine, milliseconds — and compares it to
/// a committed reference. This is the layer the 87 `#Preview`s should feed.
///
/// Determinism: we pin `scale` and the reference OS. Baselines are recorded on
/// **macOS 26** (the deployment floor); a 26↔27 render drift is a real signal,
/// not noise, so we don't silently tolerate it — record on 26, run on both.
///
/// Usage:
///
///     @Test @MainActor
///     func emptyLibraryReadsAsCalm() throws {
///         try assertSnapshot(of: LibraryEmptyState(), size: .init(width: 320, height: 200),
///                            named: "library-empty")
///     }
///
/// First run for a name with no reference RECORDS it and fails (never a silent
/// pass), so a new snapshot is reviewed like any other committed artifact. Set
/// `FICHERO_RECORD_SNAPSHOTS=1` to re-record all.
enum Snapshot {
    /// Per-pixel channel tolerance (0–255) and the max fraction of pixels that
    /// may exceed it. Font anti-aliasing jitters a hair; a real layout change
    /// moves far more than this. ponytail: fixed knobs, tighten if a real
    /// regression ever slips under them.
    static let channelTolerance: UInt8 = 4
    static let maxDifferingFraction = 0.002

    static var recordingAll: Bool {
        ProcessInfo.processInfo.environment["FICHERO_RECORD_SNAPSHOTS"] == "1"
    }

    /// Directory holding committed reference PNGs, next to the tests.
    static func referenceDir(file: String = #filePath) -> URL {
        URL(filePathString: file)
            .deletingLastPathComponent()
            .appendingPathComponent("__Snapshots__", isDirectory: true)
    }
}

@MainActor
func assertSnapshot<V: View>(
    of view: V,
    size: CGSize,
    named name: String,
    record: Bool = false,
    file: String = #filePath,
    sourceLocation: SourceLocation = #_sourceLocation
) throws {
    let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
    renderer.scale = 2
    guard let cg = renderer.cgImage else {
        Issue.record("ImageRenderer produced no image for '\(name)'", sourceLocation: sourceLocation)
        return
    }
    guard let png = Snapshot.pngData(cg) else {
        Issue.record("could not PNG-encode snapshot '\(name)'", sourceLocation: sourceLocation)
        return
    }

    let dir = Snapshot.referenceDir(file: file)
    let ref = dir.appendingPathComponent("\(name).png")

    if record || Snapshot.recordingAll || !FileManager.default.fileExists(atPath: ref.path) {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try png.write(to: ref)
        Issue.record(
            "recorded new snapshot '\(name)' — review and commit \(ref.lastPathComponent); rerun to compare",
            sourceLocation: sourceLocation
        )
        return
    }

    let refData = try Data(contentsOf: ref)
    guard let refImage = Snapshot.cgImage(from: refData) else {
        Issue.record("reference '\(name)' is not a readable PNG", sourceLocation: sourceLocation)
        return
    }
    if let diff = Snapshot.diff(cg, refImage) {
        Issue.record(
            "snapshot '\(name)' differs from reference: \(diff). Re-record with FICHERO_RECORD_SNAPSHOTS=1 if intended.",
            sourceLocation: sourceLocation
        )
    }
}

// MARK: - Pixel plumbing (no dependency; CoreGraphics only)

extension Snapshot {
    static func pngData(_ image: CGImage) -> Data? {
        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(
            data, UTType.png.identifier as CFString, 1, nil
        ) else { return nil }
        CGImageDestinationAddImage(dest, image, nil)
        guard CGImageDestinationFinalize(dest) else { return nil }
        return data as Data
    }

    static func cgImage(from data: Data) -> CGImage? {
        guard let src = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(src, 0, nil)
    }

    /// Returns nil when images match within tolerance, else a human description.
    static func diff(_ a: CGImage, _ b: CGImage) -> String? {
        guard a.width == b.width, a.height == b.height else {
            return "size \(a.width)x\(a.height) vs \(b.width)x\(b.height)"
        }
        guard let pa = rgbaBytes(a), let pb = rgbaBytes(b) else {
            return "could not read pixels"
        }
        let total = pa.count / 4
        var differing = 0
        var i = 0
        while i < pa.count {
            for c in 0..<4 where absDiff(pa[i + c], pb[i + c]) > channelTolerance {
                differing += 1
                break
            }
            i += 4
        }
        let fraction = Double(differing) / Double(max(total, 1))
        return fraction > maxDifferingFraction
            ? String(format: "%.3f%% of pixels differ (limit %.3f%%)", fraction * 100, maxDifferingFraction * 100)
            : nil
    }

    private static func absDiff(_ x: UInt8, _ y: UInt8) -> UInt8 { x > y ? x - y : y - x }

    private static func rgbaBytes(_ image: CGImage) -> [UInt8]? {
        let w = image.width, h = image.height
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        let space = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(
            data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return nil }
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        return bytes
    }
}

private extension URL {
    init(filePathString: String) {
        if #available(macOS 13.0, *) { self.init(filePath: filePathString) }
        else { self.init(fileURLWithPath: filePathString) }
    }
}
