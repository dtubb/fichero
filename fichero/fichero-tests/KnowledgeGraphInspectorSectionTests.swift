@testable import Fichero
import XCTest

@MainActor
final class KnowledgeGraphInspectorSectionTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testVisibleItemsCapsWhenCollapsed() {
        let items = (1...12).map(String.init)

        let visible = KnowledgeGraphInspectorSection.visibleItems(items, showingAll: false)

        XCTAssertEqual(visible.count, 10)
        XCTAssertEqual(visible, Array(items.prefix(10)))
    }

    func testShowAllButtonTitleReflectsState() {
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: false),
            "Show all (12)"
        )
        XCTAssertEqual(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 12, showingAll: true),
            "Show less"
        )
        XCTAssertNil(
            KnowledgeGraphInspectorSection.showAllButtonTitle(itemCount: 10, showingAll: false)
        )
    }

    func testWebPaneEntitySelectionDoesNotOpenSourceDocument() throws {
        let source = try Self.appSource("Views/Library/DocumentKGWebPane.swift")
        guard let entityCase = source.range(of: "case \"entitySelected\":"),
              let claimCase = source.range(of: "case \"claimSelected\":", range: entityCase.upperBound..<source.endIndex)
        else {
            XCTFail("DocumentKGWebPane must handle entitySelected before claimSelected")
            return
        }

        let entityHandler = String(source[entityCase.lowerBound..<claimCase.lowerBound])
        XCTAssertTrue(entityHandler.contains("focusEntity(entityId: entityId)"))
        XCTAssertFalse(entityHandler.contains("focusKGSource("))
        XCTAssertFalse(entityHandler.contains("postOpenClaimSource("))
        XCTAssertFalse(entityHandler.contains("sourceDocumentId"))
    }

    func testInspectorEntitiesTabUsesInspectorEndpointSourceOfTruth() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )

        XCTAssertTrue(source.contains("listInspectorEntitiesForDocument"))
        XCTAssertFalse(source.contains("listEntitiesForDocument(documentId: documentId)"))
    }

    func testInspectorEntitiesTabDistinguishesLoadedButHiddenEntities() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )

        XCTAssertTrue(source.contains("Loaded \\(entities.count) entities, but the current filter hides every kind."))
        XCTAssertTrue(source.contains("Loaded \\(entities.count) entities, but none mapped into a visible section."))
    }

    // testFetchButtonHelpersExposeExpectedLabelsAndIcons removed: the
    // KnowledgeGraphInspectorSection.fetchButtonHelp(for:)/fetchButtonIcon(for:)
    // helpers no longer exist in production, so the test no longer compiles.

    func testArtifactsTabIncludesPageArtifactsForParentPDFOnly() {
        let parentPDF = makeDocument(docType: .file, fileType: .pdf)
        XCTAssertTrue(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: parentPDF,
                mode: .artifactsOnly
            )
        )

        let page = makeDocument(docType: .page, fileType: nil, parentId: parentPDF.id)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: page,
                mode: .artifactsOnly
            )
        )

        let folder = makeDocument(docType: .folder, fileType: nil)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: folder,
                mode: .artifactsOnly
            )
        )

        let image = makeDocument(docType: .file, fileType: .image)
        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: image,
                mode: .artifactsOnly
            )
        )

        XCTAssertFalse(
            DocumentInspectorContentV2.shouldIncludeDescendantArtifacts(
                for: parentPDF,
                mode: .pageContentOnly
            )
        )
    }

    func testEpistemologyReducerAggregatesWeightAcrossPairRegardlessOfDirection() {
        let reduced = EpistemologyGraphReducer.reduce(
            edges: [
                EpistemologyGraphEdgeInput(
                    sourceId: "a",
                    targetId: "b",
                    predicate: "supports",
                    claimId: "c1",
                    sourceDocumentId: "d1",
                    sourcePageLabel: "1"
                ),
                EpistemologyGraphEdgeInput(
                    sourceId: "b",
                    targetId: "a",
                    predicate: "contradicts",
                    claimId: "c2",
                    sourceDocumentId: "d2",
                    sourcePageLabel: "2"
                )
            ],
            allowedNodeIds: ["a", "b"],
            maxEdges: 10
        )

        XCTAssertEqual(reduced.count, 1)
        XCTAssertEqual(reduced[0].weight, 2)
    }

    func testEpistemologyReducerSkipsEdgesOutsideVisibleNodes() {
        let reduced = EpistemologyGraphReducer.reduce(
            edges: [
                EpistemologyGraphEdgeInput(
                    sourceId: "a",
                    targetId: "b",
                    predicate: "supports",
                    claimId: "c1",
                    sourceDocumentId: "d1",
                    sourcePageLabel: nil
                ),
                EpistemologyGraphEdgeInput(
                    sourceId: "a",
                    targetId: "x",
                    predicate: "extends",
                    claimId: "c2",
                    sourceDocumentId: "d2",
                    sourcePageLabel: nil
                )
            ],
            allowedNodeIds: ["a", "b"],
            maxEdges: 10
        )

        XCTAssertEqual(reduced.count, 1)
        XCTAssertEqual(reduced[0].source, "a")
        XCTAssertEqual(reduced[0].target, "b")
    }

    func testEpistemologyReducerPrefersLongestPredicateForPair() {
        let reduced = EpistemologyGraphReducer.reduce(
            edges: [
                EpistemologyGraphEdgeInput(
                    sourceId: "a",
                    targetId: "b",
                    predicate: "supports",
                    claimId: "c1",
                    sourceDocumentId: "d1",
                    sourcePageLabel: nil
                ),
                EpistemologyGraphEdgeInput(
                    sourceId: "a",
                    targetId: "b",
                    predicate: "directly contradicts",
                    claimId: "c2",
                    sourceDocumentId: "d2",
                    sourcePageLabel: nil
                )
            ],
            allowedNodeIds: ["a", "b"],
            maxEdges: 10
        )

        XCTAssertEqual(reduced.count, 1)
        XCTAssertEqual(reduced[0].predicate, "directly contradicts")
    }

    func testHeuristicReviewMetricsReviewedCountIsCappedByTotal() {
        XCTAssertEqual(
            HeuristicReviewSheet.reviewedCount(
                total: 2,
                processed: ["a→b", "b→c", "c→d"]
            ),
            2
        )
    }

    func testHeuristicReviewMetricsAcceptanceRateUsesReviewedOnly() {
        let rate = HeuristicReviewSheet.acceptanceRate(
            processed: ["a→b", "b→c"],
            accepted: ["a→b", "x→y"]
        )
        XCTAssertEqual(rate, 0.5, accuracy: 0.0001)
    }

    private func makeDocument(
        docType: DocType,
        fileType: FileType?,
        parentId: String? = nil
    ) -> Document {
        Document(
            id: UUID().uuidString,
            parentId: parentId,
            docType: docType,
            fileType: fileType,
            name: "Test",
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}
