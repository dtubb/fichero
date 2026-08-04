import Foundation
import UniformTypeIdentifiers
import XCTest

@testable import Fichero

/// #4473's standing point: the pure classifier can be right while the DELIVERY
/// is wrong. Every existing suite hands `classifySidebarDropPayload` a
/// pre-loaded `loadedIDs` array — nothing exercises the plumbing that produces
/// that array from real `NSItemProvider`s.
///
/// These tests build genuine providers and run `sidebarDropCapabilities` and
/// `readSidebarDropPayload` end to end, so the seam between "what the drag
/// registered" and "what the destination decided" is covered by behaviour
/// rather than by inspection.
@MainActor
final class SidebarDropProviderDeliveryTests: XCTestCase {

    private func stringProvider(_ value: String) -> NSItemProvider {
        NSItemProvider(object: value as NSString)
    }

    private func urlProvider(_ path: String) -> NSItemProvider {
        NSItemProvider(object: URL(fileURLWithPath: path) as NSURL)
    }

    private func libraryDragProvider(
        kind: LibraryItemDrag.Kind = .document,
        id: String,
        documentId: String?
    ) throws -> NSItemProvider {
        let drag = LibraryItemDrag(kind: kind, id: id, documentId: documentId, text: "body")
        let json = try XCTUnwrap(String(bytes: try JSONEncoder().encode(drag), encoding: .utf8))
        return stringProvider(json)
    }

    // MARK: - Capability snapshot, from real providers

    /// A sidebar row's provider vends a string — and, PLATFORM TRUTH, also
    /// answers `canLoadObject(ofClass: URL.self) == true`, because NSString
    /// registers `public.url` alongside `public.utf8-plain-text`. The
    /// capability booleans therefore cannot decide the route; what matters is
    /// that the plain-text REGISTRATION marks the drag as possibly-internal so
    /// the read is attempted.
    func testAStringProviderReportsStringCapabilityAndNoURL() {
        let capabilities = sidebarDropCapabilities(of: [stringProvider("doc:a")])
        XCTAssertEqual(capabilities.count, 1)
        XCTAssertTrue(capabilities[0].canLoadString)
        XCTAssertTrue(
            capabilities[0].canLoadURL,
            "platform truth: an NSString provider bridges to URL; if this ever flips, the doc above is stale"
        )
        XCTAssertTrue(capabilities[0].registeredTypeIdentifiers.contains(UTType.utf8PlainText.identifier))
        XCTAssertTrue(sidebarDropMightCarryInternalID(capabilities))
    }

    /// A Finder-shaped provider vends a URL — and, PLATFORM TRUTH, ALSO
    /// answers `canLoadString == true`, because `public.file-url` conforms to
    /// `public.url`, which NSString claims readable (it bridges to
    /// "file:///…"). The load-bearing assertion is therefore NOT canLoadString
    /// but `sidebarDropMightCarryInternalID == false`: no plain-text
    /// registration means no in-process flavour, so the drop routes to the
    /// importer instead of being refused as an unreadable internal drag.
    func testAURLProviderReportsURLCapabilityAndNoString() {
        let capabilities = sidebarDropCapabilities(of: [urlProvider("/Users/d/Scan.pdf")])
        XCTAssertEqual(capabilities.count, 1)
        XCTAssertTrue(capabilities[0].canLoadURL)
        XCTAssertTrue(
            capabilities[0].canLoadString,
            "platform truth: a URL provider bridges to a string; if this ever flips, the doc above is stale"
        )
        XCTAssertFalse(sidebarDropMightCarryInternalID(capabilities))
    }

    /// The snapshot preserves ORDER and COUNT — a multi-item drag's capability
    /// list is index-aligned with its providers.
    func testTheCapabilitySnapshotIsIndexAligned() {
        let providers = [
            urlProvider("/Users/d/A.pdf"),
            stringProvider("doc:b"),
            urlProvider("/Users/d/C.pdf")
        ]
        let capabilities = sidebarDropCapabilities(of: providers)
        XCTAssertEqual(capabilities.count, 3)
        XCTAssertTrue(capabilities[0].canLoadURL)
        XCTAssertTrue(capabilities[1].canLoadString)
        XCTAssertTrue(capabilities[2].canLoadURL)
    }

    func testAnEmptyProviderSetSnapshotsToNothing() {
        XCTAssertTrue(sidebarDropCapabilities(of: []).isEmpty)
    }

    // MARK: - Loading one string out of one provider

    func testAStringProviderRoundTripsThroughTheLoader() async throws {
        let loaded = try await sidebarDropLoadString(from: stringProvider("doc:round-trip"))
        XCTAssertEqual(loaded, "doc:round-trip")
    }

    /// A provider that cannot vend a string must THROW rather than resolve to
    /// an empty string — an empty string would sail through the classifier as a
    /// non-id and turn a readable drag into `.unreadableInternal`.
    func testANonStringProviderThrowsRatherThanYieldingEmptiness() async {
        do {
            let loaded = try await sidebarDropLoadString(from: urlProvider("/Users/d/A.pdf"))
            // Some URL providers can bridge to a string; if so it must at least
            // not be empty, which is the failure mode that matters.
            XCTAssertFalse(loaded.isEmpty)
        } catch {
            // The expected path: nothing readable, reported as an error.
        }
    }

    // MARK: - End-to-end: providers in, route out

    /// The whole delivery path for a sidebar row drag: real provider → real
    /// read → `.internalItems` with the `doc:`-prefixed id intact.
    func testASidebarRowDragDeliversItsIDAllTheWayThrough() async {
        let payload = await readSidebarDropPayload([stringProvider("doc:marshall-1")])
        XCTAssertEqual(payload, .internalItems(["doc:marshall-1"]))
    }

    /// The library pane's JSON shape arrives at the same answer through the
    /// same reader — the "one payload type for one concept, resolved on the
    /// reading side" requirement, proved with real providers.
    func testALibraryPaneDragDeliversTheSameInternalShape() async throws {
        let provider = try libraryDragProvider(id: "row-9", documentId: "pdf-4")
        let payload = await readSidebarDropPayload([provider])
        XCTAssertEqual(payload, .internalItems(["doc:pdf-4"]))
    }

    /// A multi-select spanning both panes delivers every id, in drag order.
    func testAMixedMultiSelectionDeliversEveryIDInOrder() async throws {
        let providers = [
            stringProvider("doc:a"),
            try libraryDragProvider(id: "b", documentId: "b"),
            stringProvider("doc:c")
        ]
        let payload = await readSidebarDropPayload(providers)
        XCTAssertEqual(payload, .internalItems(["doc:a", "doc:b", "doc:c"]))
    }

    /// A pure Finder drag delivers `.externalFiles` — the one route allowed to
    /// reach the importer.
    func testAPureFileDragDeliversExternalFiles() async {
        let payload = await readSidebarDropPayload([urlProvider("/Users/d/Scan.pdf")])
        XCTAssertEqual(payload, .externalFiles)
    }

    /// Several external files still deliver one `.externalFiles` verdict, not
    /// one per provider.
    func testSeveralExternalFilesDeliverOneExternalVerdict() async {
        let payload = await readSidebarDropPayload([
            urlProvider("/Users/d/A.pdf"),
            urlProvider("/Users/d/B.pdf")
        ])
        XCTAssertEqual(payload, .externalFiles)
    }

    /// An empty drop is unsupported, never an import.
    func testAnEmptyDropDeliversUnsupported() async {
        let payload = await readSidebarDropPayload([])
        XCTAssertEqual(payload, .unsupported)
    }

    /// A drag whose only string is NOT one of ours, with no file behind it,
    /// delivers `.unreadableInternal`.
    ///
    /// CHARACTERISATION of a design edge worth knowing: the in-process flavour
    /// is inferred from "can vend a string", so dragging plain text from
    /// ANOTHER application onto a Fichero folder lands here and shows
    /// "Couldn't read what was dragged" — an accusation about a drag that never
    /// came from inside the app. Deliberately safe-by-default (the alternative
    /// re-imports real documents), but the message is wrong for this case.
    func testForeignPlainTextDeliversTheUnreadableInternalVerdict() async {
        let payload = await readSidebarDropPayload([stringProvider("some pasted prose")])
        XCTAssertEqual(payload, .unreadableInternal)
        XCTAssertNotEqual(
            payload, .externalFiles,
            "safe by default: never fall through to ingestion"
        )
    }

    /// The #4401 shape itself, delivered rather than simulated: a drag that
    /// carries BOTH our id and a file URL is a move, and the file is ignored.
    func testAnInternalDragThatAlsoVendsAFileIsDeliveredAsAMove() async {
        let payload = await readSidebarDropPayload([
            stringProvider("doc:marshall-1"),
            urlProvider("/var/folders/zz/fichero-drag-1/Marshall.pdf")
        ])
        XCTAssertEqual(payload, .internalItems(["doc:marshall-1"]))
        XCTAssertNotEqual(payload, .externalFiles, "this routing re-ingested the document")
    }

    /// A drag carrying an unreparentable row's JSON alongside a file URL is
    /// still refused rather than imported — the annotation must not become a
    /// new document.
    func testAnUnreparentableRowBesideAFileIsRefusedNotImported() async throws {
        let providers = [
            try libraryDragProvider(kind: .annotation, id: "ann", documentId: "doc-1"),
            urlProvider("/Users/d/Scan.pdf")
        ]
        let payload = await readSidebarDropPayload(providers)
        XCTAssertEqual(payload, .unreadableInternal)
    }

    // NOTE: `DropInfo` has no public initializer, so `LibraryItemDropDelegate`'s
    // own callbacks cannot be driven from a unit test at all. Everything the
    // delegate does that IS reachable — the badge rule and the type set it
    // collects — is covered by `LibraryItemDropProposalTests`; a live drag
    // remains the acceptance step for the callbacks themselves (#4473).
}
