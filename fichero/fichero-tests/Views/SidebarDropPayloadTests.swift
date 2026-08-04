@testable import Fichero
import Foundation
import Testing
import UniformTypeIdentifiers

/// #4401 (P0): dragging a document between folders in the same library copied
/// instead of moving, and the copy arrived with no entities and no content.
///
/// The cause is a classifier that decided "external" by ELIMINATION. Any
/// provider that could load a URL, or registered any type identifier that was
/// not one of three plain-text ones, made the whole drop external.
///
/// That was safe only while an internal drag advertised nothing but its id.
/// #4123 then taught `SidebarDragID` to export a real file and RTF so a drag
/// OUT of the app would deposit something useful in Finder — so a document
/// row's provider began registering `public.data` and `public.rtf`, and
/// answering true to `canLoadObject(ofClass: URL.self)`. Every internal
/// document drag then classified as external files and went to
/// `importService.importFiles`, which re-ingested it as a NEW document.
///
/// Both halves of the symptom, exactly: a second document appears, and it is
/// hollow because it was freshly imported and never processed. It also
/// explains why folders moved correctly — `SidebarDragID(item:)` only sets
/// `documentId` for non-folders, so a folder exported no file and kept the
/// id-only shape.
struct SidebarDropPayloadTests {

    // MARK: - The id predicate

    @Test("only the sidebar's own id shape counts as internal")
    func onlyOurIDShapeIsInternal() {
        #expect(isInternalSidebarItemID("doc:1234-5678"))
        #expect(isInternalSidebarItemID("  doc:abc  "), "whitespace from a pasteboard is tolerated")

        // A bare prefix carries no document.
        #expect(!isInternalSidebarItemID("doc:"))
        // Things a Finder drag or a text clipping can produce.
        #expect(!isInternalSidebarItemID(""))
        #expect(!isInternalSidebarItemID("file:///Users/x/Scan.pdf"))
        #expect(!isInternalSidebarItemID("Scan.pdf"))
        #expect(!isInternalSidebarItemID("Some transcript text mentioning doc: things"))
    }

    // MARK: - The defect, stated directly

    /// The exact shape that was destroying documents: an internal drag that
    /// ALSO vends a file. It must move, not import.
    @Test("an internal drag that also vends a file is still a move")
    func internalDragThatAlsoVendsAFileIsAMove() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:marshall-1"],
            hasFileURL: true,
            carriesOwnProcessFlavor: true
        )
        #expect(payload == .internalItems(["doc:marshall-1"]))
        #expect(payload != .externalFiles, "this routing is what re-ingested the document")
    }

    /// The positive identification wins regardless of what else is advertised —
    /// which is what lets export representations be added later without
    /// silently re-routing moves.
    @Test("an internal id wins over every external signal")
    func internalIDWinsOverExternalSignals() {
        for hasFileURL in [true, false] {
            let payload = classifySidebarDropPayload(
                loadedIDs: ["doc:a", "doc:b"],
                hasFileURL: hasFileURL,
                carriesOwnProcessFlavor: true
            )
            #expect(payload == .internalItems(["doc:a", "doc:b"]))
        }
    }

    /// Multi-select drags keep every id, in order.
    @Test("every internal id is carried, in order")
    func everyInternalIDIsCarried() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:a", "not-ours", "doc:b"],
            hasFileURL: false,
            carriesOwnProcessFlavor: true
        )
        #expect(payload == .internalItems(["doc:a", "doc:b"]))
    }

    // MARK: - A genuine external drop still imports

    @Test("a Finder file drag with no internal id imports")
    func finderFileDragImports() {
        let payload = classifySidebarDropPayload(
            loadedIDs: [],
            hasFileURL: true,
            carriesOwnProcessFlavor: false
        )
        #expect(payload == .externalFiles)
    }

    @Test("a Finder drag carrying unrelated text still imports")
    func finderDragWithTextImports() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["Scan.pdf"],
            hasFileURL: true,
            carriesOwnProcessFlavor: false
        )
        #expect(payload == .externalFiles)
    }

    // MARK: - Never silently re-import something already here

    /// The rule this issue turns on: a drag that started INSIDE the app and
    /// cannot be read is a bug to report, not a case to fall back to
    /// ingestion. Falling back is what produced the hollow duplicate.
    @Test("an unreadable internal drag refuses rather than importing")
    func unreadableInternalDragRefuses() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["some transcript that is not an id"],
            hasFileURL: true,
            carriesOwnProcessFlavor: true
        )
        #expect(payload == .unreadableInternal)
        #expect(payload != .externalFiles, "re-importing an item already in the library is the data loss")
    }

    @Test("an unreadable internal drag with no id at all also refuses")
    func unreadableInternalWithNoStringsRefuses() {
        #expect(
            classifySidebarDropPayload(loadedIDs: [], hasFileURL: true, carriesOwnProcessFlavor: true)
                == .unreadableInternal
        )
    }

    /// The property that matters: **no input that came from inside the app can
    /// ever route to an import.** This is the assertion that makes the data
    /// loss structurally impossible rather than merely fixed.
    @Test("nothing from inside the app can ever route to an import")
    func nothingInternalEverImports() {
        let idSets: [[String]] = [
            [], ["doc:a"], ["doc:a", "doc:b"], ["not-an-id"], ["", "doc:"], ["transcript text"]
        ]
        for ids in idSets {
            for hasFileURL in [true, false] {
                let payload = classifySidebarDropPayload(
                    loadedIDs: ids,
                    hasFileURL: hasFileURL,
                    carriesOwnProcessFlavor: true
                )
                #expect(payload != .externalFiles, "ids: \(ids), hasFileURL: \(hasFileURL)")
            }
        }
    }

    @Test("an empty drop is unsupported, not an import")
    func emptyDropIsUnsupported() {
        #expect(
            classifySidebarDropPayload(loadedIDs: [], hasFileURL: false, carriesOwnProcessFlavor: false)
                == .unsupported
        )
    }

    // MARK: - Structural: the import path is unreachable from an internal drag

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The routing must happen AFTER the ids are read. Deciding from provider
    /// capabilities alone is what could not tell an internal document drag from
    /// a Finder file drag, since #4123 made both advertise a file.
    @Test("the drop reads its ids before it routes")
    func theDropReadsBeforeItRoutes() throws {
        // 6c1519367 (#4474/#4475): the row no longer reads providers itself —
        // it calls readSidebarDropPayload, and the read-before-route ordering
        // lives in that ONE shared reader. Pin both halves: the row defers to
        // the reader, and the reader appends every loaded id before it asks
        // the classifier for a route.
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")
        let body = source.components(separatedBy: "func handleRowDrop(").dropFirst().first ?? ""
        #expect(body.contains("readSidebarDropPayload(providers)"))

        let reader = try Self.appSource("Views/Sidebar/ItemRow/SidebarDropProviderReader.swift")
        let readerBody = reader.components(separatedBy: "func readSidebarDropPayload(")
            .dropFirst().first ?? ""
        let load = readerBody.range(of: "loadedIDs.append")
        let route = readerBody.range(of: "classifySidebarDropPayload(")
        #expect(load != nil)
        #expect(route != nil)
        if let load, let route {
            #expect(load.lowerBound < route.lowerBound, "ids must be read before the route is chosen")
        }
    }

    /// Only the external branch may reach the importer, and the unreadable
    /// branch must report instead.
    @Test("the import path is reachable only from the external branch")
    func importIsReachableOnlyFromExternal() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")
        let body = source.components(separatedBy: "func handleRowDrop(")[1]

        // The internal branch moves.
        #expect(body.contains("case .internalItems(let ids):"))
        #expect(body.contains("handleDropIntoFolder(itemIDs: ids, targetFolder: item)"))
        // The unreadable branch reports and does NOT import.
        #expect(body.contains("case .unreadableInternal:"))
        #expect(body.contains("dropErrorMessage"))

        let unreadable = body.components(separatedBy: "case .unreadableInternal:")[1]
        let untilNextCase = unreadable.components(separatedBy: "case .unsupported")[0]
        #expect(!untilNextCase.contains("handleProvidersDrop"))
        #expect(!untilNextCase.contains("importFiles"))
    }

    // MARK: - #4459: a drop the OS was told was accepted must not vanish silently

    /// `handleProvidersDrop`'s sync `Bool` return tells the OS the drop was
    /// accepted before the async load even starts — the API gives no other
    /// option. If every provider then fails to load, that must surface
    /// somewhere the user is looking, not just a log line: an accepted drop
    /// that produces nothing, with no explanation, is the exact "did it
    /// work?" shape rule zero exists to close.
    @Test("every provider failing to load reports to the user, not just the log")
    func allLoadsFailingReportsToTheUser() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        let body = source.components(separatedBy: "func handleProvidersDrop(")[1]
        let guardClause = body.components(
            separatedBy: "guard !stableURLs.isEmpty || !tempURLs.isEmpty else {"
        )[1].components(separatedBy: "\n            }")[0]
        #expect(
            guardClause.contains("sidebarState.dropErrorMessage ="),
            "total load failure must set the same user-visible banner import failures use"
        )
    }
}
