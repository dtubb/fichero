//
//  ReaderProxyDragIdentityTests.swift
//  FicheroTests
//
//  Daniel, live 2026-09-02: dragging the reader's proxy icon "should be a way
//  to feed the document/artifact into the workflow bar's With slot (run a
//  workflow on it)".
//
//  The drag side is this: the proxy icon's NSItemProvider now registers the
//  app's own `UTType.ficheroDragItem` — a `LibraryItemDrag` as JSON, the SAME
//  in-app flavor every library row and sidebar row exports — ALONGSIDE the
//  Markdown file and plain text it already promised. Registration ORDER is the
//  preference order, so a Finder or editor drop still receives the .md file
//  exactly as before; only an in-app destination sees the identity.
//
//  These pin the payload contract the drop side (workflow bar, another lane)
//  reads:
//    kind .artifact          → RunScope.artifact(documentId:artifactId:…)
//    kind .document / .page  → RunScope.documents(ids: [id])
//

import Foundation
import Testing
import UniformTypeIdentifiers
@testable import Fichero

struct ReaderProxyDragIdentityTests {

    private func drag(kind: LibraryItemDrag.Kind, id: String, documentId: String?) -> LibraryItemDrag {
        LibraryItemDrag(
            kind: kind, id: id, documentId: documentId, text: "Page one.", name: "1933"
        )
    }

    @Test("the proxy icon registers the app's own in-app flavor when given an identity")
    func registersFicheroDragItem() throws {
        let provider = try #require(ReaderMarkdownDrag.itemProvider(
            text: "Page one.",
            documentName: "1933",
            identity: drag(kind: .document, id: "doc-1", documentId: "doc-1")
        ))
        #expect(
            provider.registeredTypeIdentifiers.contains(UTType.ficheroDragItem.identifier),
            """
            Without the named flavor an in-app drop target sees only Markdown \
            and plain text — it can promise the WORDS but not say which node \
            they came from, so a workflow cannot be run on it.
            """
        )
    }

    @Test("the Markdown and plain-text promises survive the addition")
    func keepsExistingCrossAppPromises() throws {
        let provider = try #require(ReaderMarkdownDrag.itemProvider(
            text: "Page one.",
            documentName: "1933",
            identity: drag(kind: .document, id: "doc-1", documentId: "doc-1")
        ))
        let ids = provider.registeredTypeIdentifiers
        #expect(ids.contains(UTType.utf8PlainText.identifier))
        #expect(ids.contains(ReaderMarkdownDrag.contentType.identifier))
        #expect(provider.suggestedName == "1933.md")
    }

    @Test("the in-app flavor is FIRST, so it wins for an in-app drop")
    func inAppFlavorIsPreferred() throws {
        let provider = try #require(ReaderMarkdownDrag.itemProvider(
            text: "Page one.",
            documentName: "1933",
            identity: drag(kind: .artifact, id: "art-9", documentId: "doc-1")
        ))
        #expect(
            provider.registeredTypeIdentifiers.first == UTType.ficheroDragItem.identifier,
            """
            NSItemProvider treats registration order as preference order. \
            Behind the plain-text flavor, an in-app target that accepts text \
            would take the transcript instead of the identity.
            """
        )
    }

    @Test("no identity keeps the drag exactly as it was")
    func identityIsOptional() throws {
        let provider = try #require(ReaderMarkdownDrag.itemProvider(
            text: "Page one.", documentName: "1933"
        ))
        #expect(!provider.registeredTypeIdentifiers.contains(UTType.ficheroDragItem.identifier))
    }

    @Test("an empty transcript is still not draggable")
    func emptyTextStillVendsNothing() {
        #expect(ReaderMarkdownDrag.itemProvider(
            text: "   \n ",
            documentName: "1933",
            identity: drag(kind: .document, id: "doc-1", documentId: "doc-1")
        ) == nil)
    }

    // MARK: - The payload contract the workflow bar's "With" slot reads

    @Test("an artifact payload carries BOTH ids — the drop needs the document too")
    func artifactPayloadRoundTrips() throws {
        let payload = drag(kind: .artifact, id: "art-9", documentId: "doc-1")
        let decoded = try JSONDecoder().decode(
            LibraryItemDrag.self, from: JSONEncoder().encode(payload)
        )
        #expect(decoded.kind == .artifact)
        // RunScope.artifact takes documentId AND artifactId: a run targets the
        // DOCUMENT and carries the artifact so an artifacts_source step reads
        // that one rather than its default.
        #expect(decoded.id == "art-9")
        #expect(decoded.documentId == "doc-1")
    }

    @Test("a document payload round-trips to the id a run is dispatched with")
    func documentPayloadRoundTrips() throws {
        let payload = drag(kind: .page, id: "page-3", documentId: "page-3")
        let decoded = try JSONDecoder().decode(
            LibraryItemDrag.self, from: JSONEncoder().encode(payload)
        )
        #expect(decoded.kind == .page)
        #expect(decoded.id == "page-3")
    }

    @Test("the reader builds the identity from what the HEAD says it is showing")
    func identityFollowsTheArtifactLens() throws {
        let repoRoot = try AppSource.root()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let source = try String(
            contentsOf: repoRoot.appendingPathComponent(
                "fichero/fichero/Views/Reader/Page/ReadingPaneView.swift"
            ),
            encoding: .utf8
        )
        #expect(source.contains("func readerProxyIdentity("))
        #expect(
            source.contains("if let lens = artifactLens {"),
            """
            The lens must outrank the document: the head NAMES the artifact it \
            is pointed at, and a proxy icon that drags something the head does \
            not name is the head lying.
            """
        )
        #expect(source.contains("kind: .artifact"))
        #expect(source.contains("identity: readerProxyIdentity(for: document, text: text)"))
    }
}
