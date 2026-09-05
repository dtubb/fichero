// Stage A2 — macOS 26 Vision `RecognizeDocumentsRequest`, the third arm.
//
// Fichero's engine still calls the OLD `VNRecognizeTextRequest` everywhere
// (vision_base.py:1734), which is the arm that fragments a diary page into 403
// "lines" for 966 words. macOS 26 added a document-structure request that
// returns lines, paragraphs and words as containers, each carrying a region —
// and it is Swift-only (new struct-based Vision API), so pyobjc cannot reach
// it and this small harness exists.
//
// It writes the SAME JSON shape as kraken_segment.py, including the pixel
// frame every record must name, so one renderer draws all three arms and the
// comparison is polygon-to-polygon rather than polygon-to-adjective.
//
// Build + run (needs the macOS 26 SDK):
//   DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer \
//     swiftc -O RecognizeDocuments.swift -o /tmp/recognize-documents
//   /tmp/recognize-documents OUT_DIR PAGE [PAGE ...]

import AppKit
import Foundation
import Vision
import simd

struct LineRecord: Codable {
    let index: Int
    let text: String
    let polygon: [[Double]]
    let bbox: [Double]?
}

struct PageRecord: Codable {
    let page: String
    let source_path: String
    let pixel_frame: [String: Int]
    let engine: String
    let seconds: Double
    let line_count: Int
    let word_count: Int
    let error: String?
    let lines: [LineRecord]
    let words: [LineRecord]
}

/// Vision normalizes to a LOWER-LEFT origin; the shared OCR geometry contract
/// (and every other provider parser in media/ocr_geometry.py) is top-left. Flip
/// here, at the boundary, exactly as `_vision_flip_bbox_to_top_left` does on
/// the Python side — never later, where a silent half-page offset looks like a
/// bad model rather than a bad convention.
func flippedPolygon(_ points: [simd_float2]) -> [[Double]] {
    points.map { [Double($0.x), 1.0 - Double($0.y)] }
}

func boundingBox(of polygon: [[Double]]) -> [Double]? {
    guard let first = polygon.first else { return nil }
    var minX = first[0], maxX = first[0], minY = first[1], maxY = first[1]
    for point in polygon {
        minX = min(minX, point[0]); maxX = max(maxX, point[0])
        minY = min(minY, point[1]); maxY = max(maxY, point[1])
    }
    return [minX, minY, maxX - minX, maxY - minY]
}

func record(_ observation: RecognizedTextObservation, index: Int) -> LineRecord {
    let polygon = flippedPolygon(observation.boundingRegion.normalizedPoints)
    return LineRecord(
        index: index,
        text: observation.transcript,
        polygon: polygon,
        bbox: boundingBox(of: polygon)
    )
}

func pixelSize(of url: URL) -> (Int, Int) {
    guard let image = NSImage(contentsOf: url),
          let rep = image.representations.first else { return (0, 0) }
    return (rep.pixelsWide, rep.pixelsHigh)
}

// No `@main`: swiftc compiles a lone file as top-level code, and the two
// cannot coexist. The work is an async function driven from the bottom of the
// file instead.
func run() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        guard arguments.count >= 2 else {
            FileHandle.standardError.write(Data("usage: recognize-documents OUT_DIR PAGE...\n".utf8))
            exit(2)
        }
        let outDir = URL(fileURLWithPath: arguments[0], isDirectory: true)
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        for path in arguments.dropFirst() {
            let url = URL(fileURLWithPath: path)
            let (width, height) = pixelSize(of: url)
            let began = Date()
            var lines: [LineRecord] = []
            var words: [LineRecord] = []
            var failure: String? = nil

            do {
                let request = RecognizeDocumentsRequest()
                let observations = try await request.perform(on: url)
                FileHandle.standardError.write(Data("observations=\(observations.count)\n".utf8))
                for observation in observations {
                    let region = observation.document.boundingRegion.normalizedPoints
                    let xs = region.map { Double($0.x) }, ys = region.map { Double($0.y) }
                    FileHandle.standardError.write(Data(
                        "  container x[\(xs.min() ?? 0)..\(xs.max() ?? 0)] y[\(ys.min() ?? 0)..\(ys.max() ?? 0)]\n".utf8))
                    let text = observation.document.text
                    for (index, line) in text.lines.enumerated() {
                        lines.append(record(line, index: index))
                    }
                    for (index, word) in (text.words ?? []).enumerated() {
                        words.append(record(word, index: index))
                    }
                }
            } catch {
                failure = "\(type(of: error)): \(error)"
            }

            let payload = PageRecord(
                page: url.lastPathComponent,
                source_path: url.path,
                pixel_frame: ["width": width, "height": height],
                engine: "vision-recognize-documents",
                seconds: (Date().timeIntervalSince(began) * 10).rounded() / 10,
                line_count: lines.count,
                word_count: words.count,
                error: failure,
                lines: lines,
                words: words
            )

            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let target = outDir.appendingPathComponent(
                url.deletingPathExtension().lastPathComponent + ".documents.json"
            )
            if let data = try? encoder.encode(payload) {
                try? data.write(to: target)
            }
            print("\(url.lastPathComponent): \(lines.count) lines, \(words.count) words, "
                  + "\(payload.seconds)s, frame \(width)x\(height), err=\(failure ?? "none")")
        }
}

let done = DispatchSemaphore(value: 0)
Task {
    await run()
    done.signal()
}
done.wait()
