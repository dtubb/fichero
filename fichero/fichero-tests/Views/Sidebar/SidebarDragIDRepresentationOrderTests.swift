import XCTest

/// Guardrail for #4401 — the in-process id must be the FIRST representation
/// `SidebarDragID` exports.
///
/// #4401's fix made `handleRowDrop` identify an internal drag POSITIVELY, by
/// asking each provider for a string and looking for our id, rather than by the
/// absence of anything external. That is the right predicate, but it is only as
/// good as which string the provider hands back.
///
/// `NSItemProvider.loadObject(ofClass: NSString.self)` returns the FIRST
/// representation an `NSString` can be constructed from, in REGISTRATION order.
/// `SidebarDragID` exports the transcript as `.utf8PlainText` *and* the id as a
/// `ProxyRepresentation` — both satisfy `NSString`. While the id was registered
/// last, every document with a transcript (`exportsText` is
/// `!transcript.isEmpty`, so: every transcribed document, which is the whole
/// Marshall corpus) handed back the TRANSCRIPT. No id was ever found, the drag
/// classified as `.unreadableInternal`, and the move was REFUSED.
///
/// That failed safe — nothing was duplicated, and the refusal was visible — but
/// transcribed documents could not be filed at all.
///
/// Ordering is safe to change here precisely because the id carries
/// `.visibility(.ownProcess)`: no other application can see that representation
/// at ANY position, so its position only ever decided what this app's own reader
/// got. The cross-app exports below it are unchanged.
final class SidebarDragIDRepresentationOrderTests: XCTestCase {
    /// The id must precede the plain-text transcript, or `loadObject` resolves
    /// the transcript and the id is never seen.
    func testIdProxyIsRegisteredBeforeThePlainTextTranscript() throws {
        let body = try Self.transferRepresentationBody()
        guard let idIndex = body.range(of: "ProxyRepresentation(exporting: \\.id)")?.lowerBound,
              let textIndex = body.range(of: "exportedContentType: .utf8PlainText")?.lowerBound else {
            return XCTFail("Expected both the id ProxyRepresentation and the utf8PlainText export (#4401).")
        }
        XCTAssertTrue(
            idIndex < textIndex,
            """
            SidebarDragID must register the id ProxyRepresentation BEFORE the \
            utf8PlainText transcript. loadObject(ofClass: NSString.self) returns the \
            first NSString-convertible representation, so a transcript registered \
            first makes every transcribed document's drag unreadable and refused (#4401).
            """
        )
    }

    /// The same collision exists with the RTF transcript for any consumer that
    /// coerces rich text to a string, so the id leads the whole export list.
    func testIdProxyIsTheFirstRepresentationDeclared() throws {
        let body = try Self.transferRepresentationBody()
        guard let idIndex = body.range(of: "ProxyRepresentation(exporting: \\.id)")?.lowerBound else {
            return XCTFail("Expected the id ProxyRepresentation (#4401).")
        }
        for other in ["FileRepresentation(", "exportedContentType: .rtf"] {
            guard let otherIndex = body.range(of: other)?.lowerBound else { continue }
            XCTAssertTrue(
                idIndex < otherIndex,
                "The id ProxyRepresentation must be declared before \(other) (#4401)."
            )
        }
    }

    /// Ordering is only safe because the id is invisible outside this process.
    /// If that visibility is ever dropped, moving the id first WOULD start
    /// handing other apps a "doc:<uuid>" clipping instead of the real file — so
    /// the two facts have to be pinned together.
    func testIdProxyStaysOwnProcessOnly() throws {
        let body = try Self.transferRepresentationBody()
        XCTAssertTrue(
            body.contains(".visibility(.ownProcess)"),
            """
            The id ProxyRepresentation must stay .ownProcess. It is registered first \
            for the in-app reader's benefit; without ownProcess visibility that \
            position would also make external drags export the id instead of the \
            source file (#4401).
            """
        )
    }

    /// Isolate `transferRepresentation`'s body so a match elsewhere in the file
    /// cannot satisfy an ordering assertion.
    private static func transferRepresentationBody() throws -> String {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        guard let start = source.range(of: "static var transferRepresentation: some TransferRepresentation {") else {
            throw XCTSkip("SidebarDragID.transferRepresentation not found — the drag contract moved.")
        }
        let rest = source[start.upperBound...]
        guard let end = rest.range(of: "\n    }\n") else { return String(rest) }
        return String(rest[..<end.lowerBound])
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
