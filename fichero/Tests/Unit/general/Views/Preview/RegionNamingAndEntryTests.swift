#if os(macOS)
@testable import Fichero
import Foundation
import Testing

/// Daniel, 2026-08-31: "if we draw it, we should be able to save it, and
/// double click on it to be taken to a new region. Marquee select can do that
/// — then you right-mouse-click to make a new region, or have an icon beside
/// it, which lets you give it a name."
///
/// The naming half is pure and unit-testable; the wiring half (which gesture
/// enters a region, which request carries the name) is pinned as a source
/// surface, the same idiom the containment-ladder guards use — the preview's
/// gestures cannot be synthesized in-process.
struct RegionNamingAndEntryTests {

    // MARK: - The pure half

    @Test("a single named region keeps the name exactly as typed")
    func singleRegionKeepsTheName() {
        #expect(ZoomableImagePreview.childName("Entry", offset: 0, total: 1) == "Entry")
    }

    @Test("a set under one name is numbered, so the nodes stay distinguishable")
    func setIsNumbered() {
        #expect(ZoomableImagePreview.childName("Entry", offset: 0, total: 3) == "Entry 1")
        #expect(ZoomableImagePreview.childName("Entry", offset: 2, total: 3) == "Entry 3")
    }

    @Test("an empty name stays empty — an unnamed region is not renamed at all")
    func emptyNameStaysEmpty() {
        #expect(ZoomableImagePreview.childName("", offset: 0, total: 1).isEmpty)
        #expect(ZoomableImagePreview.childName("", offset: 1, total: 4).isEmpty)
    }

    // MARK: - The armed-request half

    @Test("the whole-set request anchors on the first badge, and only the first")
    @MainActor
    func wholeSetAnchorsOnFirstBadge() {
        let request = RegionNamingRequest.shared
        request.arm(documentId: "doc-1", marqueeIndex: nil)
        #expect(request.anchors(documentId: "doc-1", index: 0))
        #expect(!request.anchors(documentId: "doc-1", index: 1))
        // A request armed over one page must never re-open over another.
        #expect(!request.anchors(documentId: "doc-2", index: 0))
        request.clear()
    }

    @Test("a badge request anchors on ITS marquee, not the first")
    @MainActor
    func badgeRequestAnchorsOnItsOwnMarquee() {
        let request = RegionNamingRequest.shared
        request.arm(documentId: "doc-1", marqueeIndex: 2)
        #expect(request.anchors(documentId: "doc-1", index: 2))
        #expect(!request.anchors(documentId: "doc-1", index: 0))
        request.clear()
        #expect(!request.isArmed)
        #expect(!request.anchors(documentId: "doc-1", index: 2))
    }

    @Test("arming a new request drops the previous name — never a stale label")
    @MainActor
    func armingResetsTheName() {
        let request = RegionNamingRequest.shared
        request.arm(documentId: "doc-1", marqueeIndex: 0)
        request.name = "Left column"
        request.arm(documentId: "doc-1", marqueeIndex: 1)
        #expect(request.name.isEmpty)
        request.clear()
    }

    // MARK: - The wiring half

    private func source(_ rel: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(rel), encoding: .utf8
        )
    }

    @Test("a double-click enters a region without costing the selection")
    func doubleClickSelectsThenEnters() throws {
        let layer = try source(
            "Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift"
        )
        // The pointer now arrives from AppKit (2026-09-01): a double-click is
        // clickCount == 2 on mouse-down, and the layer selects THEN enters —
        // the same select-then-enter pairing the ruling asks for.
        #expect(layer.contains("if clickCount == 2 {"))
        #expect(layer.contains("handleTap(at: point, in: size)\n            handleOpen(at: point, in: size)"))
        #expect(layer.contains("onOpenRegion(boxes[picked].index)"))
        // And the layer itself never owns a gesture: that is what starved the
        // scroll view of pan/pinch/swipe.
        #expect(!layer.contains(".gesture("))
        #expect(!layer.contains("SpatialTapGesture"))
        #expect(layer.contains(".allowsHitTesting(false)"))
    }

    @Test("entering a region opens its child node, and only zooms as a fallback")
    func openRegionPrefersTheChildNode() throws {
        let entry = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+RegionEntry.swift"
        )
        // The child is matched by the rect it names in the PARENT's frame —
        // a rect measured on another rendition would place a plausible node
        // behind the wrong box.
        #expect(entry.contains("region.isInParentFrame"))
        #expect(entry.contains("RegionInteractionLayer.sameExtent(region.rect, bbox"))
        #expect(entry.contains("onNavigateToDocument(match.id)"))
        // No node behind the box: zoom, never invent one.
        #expect(entry.contains("imageCoordinator?.zoomToNormalizedRegion(bbox)"))
    }

    @Test("a just-promoted region is enterable immediately, not after a reload")
    func freshChildIsEnterable() throws {
        let entry = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+RegionEntry.swift"
        )
        // The parent's children cache predates the new child; `children(of:)`
        // answers from that cache, so it must be dropped at creation or the
        // double-click silently falls back to a zoom.
        #expect(entry.contains("documentStore.childrenCache[parentId] = nil"))
        // …and the id-based navigation only sees the CURRENT listing, so the
        // listing steps into the page when the child is not in it yet.
        #expect(entry.contains("await documentStore.loadChildren(of: page)"))
        #expect(entry.contains("documentStore.currentDocuments.contains { $0.id == match.id }"))
    }

    @Test("both naming routes commit through one promote path")
    func bothRoutesShareOnePromote() throws {
        let regions = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift"
        )
        // The right-click verb ARMS naming rather than promoting immediately.
        #expect(regions.contains("RegionNamingRequest.shared.arm(documentId: documentId, marqueeIndex: nil)"))
        #expect(regions.contains("New Region from Selection…"))
        #expect(regions.contains("promoteMarquees(named: name, onlyIndex: index)"))
        // A promoted marquee lands as BOTH a drawable box and a node to enter.
        #expect(regions.contains("artifactService.addRegion("))
        #expect(regions.contains("materializeRegionChild("))
    }

    @Test("the name rides the rename path, because no create request carries one")
    func nameRidesTheRenamePath() throws {
        let entry = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+RegionEntry.swift"
        )
        #expect(entry.contains("service.cropChild("))
        #expect(entry.contains("documentStore.renameDocumentById(childId, to: name)"))
        // An unnamed region is created and left alone — never renamed to "".
        #expect(entry.contains("guard !name.isEmpty else { return }"))
    }
}

#endif
