@testable import Fichero
import SwiftUI
import XCTest

/// Renders each dataset renderer over the preview fixture and writes PNGs to
/// /tmp/dataset-previews — the same fixture the #Preview blocks use, so the
/// visuals can be iterated headlessly (Daniel 2026-08-14: "use xcode preview
/// for the various views so you can get them visually good, without having
/// to work about data layer"). The assertion is only "it rendered non-empty";
/// the PNGs are the review surface.
@MainActor
final class DatasetRendererSnapshotTests: XCTestCase {
    private func snapshot(_ view: some View, size: CGSize, name: String) throws {
        let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.nsImage, "\(name) rendered nothing")
        XCTAssertGreaterThan(image.size.width, 0)
        let dir = URL(fileURLWithPath: "/tmp/dataset-previews", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let tiff = try XCTUnwrap(image.tiffRepresentation)
        let rep = try XCTUnwrap(NSBitmapImageRep(data: tiff))
        let png = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }

    func testRenderersProduceNonEmptySnapshots() throws {
        let store = DatasetModeStore.previewDiary()
        try snapshot(DatasetCalendarView(store: store), size: .init(width: 720, height: 640),
                     name: "calendar")
        try snapshot(DatasetCardsView(store: store), size: .init(width: 780, height: 640),
                     name: "cards")
        try snapshot(DatasetTimelineView(store: store), size: .init(width: 640, height: 640),
                     name: "timeline")
        try snapshot(DatasetMissingRoleView(role: "date", renderer: "calendar"),
                     size: .init(width: 560, height: 400), name: "missing-role")
    }
}
