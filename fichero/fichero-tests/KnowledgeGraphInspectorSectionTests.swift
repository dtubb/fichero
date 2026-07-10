@testable import Fichero
import FicheroAPIClient
import XCTest

// swiftlint:disable file_length type_body_length
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

    func testGroupedItemDetectsChildClaims() {
        let child = GroupedItem.ExtraClaim(
            claimId: "claim-2",
            context: "child context",
            sourceDocumentId: "doc-2",
            sourcePageLabel: "page 2",
            sourceExcerpt: nil
        )
        let item = GroupedItem(
            claimId: "claim-1",
            displayName: "Ada Lovelace",
            context: "primary context",
            aliases: [],
            extraClaims: [child]
        )
        let leaf = GroupedItem(
            claimId: "claim-3",
            displayName: "Grace Hopper",
            context: "primary context",
            aliases: []
        )

        XCTAssertTrue(item.includesChildren)
        XCTAssertFalse(leaf.includesChildren)
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
        // After the EntityStore migration, the view calls the store; the store calls the endpoint.
        let storeSource = try Self.appSource("Models/EntityStore.swift")

        XCTAssertTrue(source.contains("entityStore.loadEntities(forDocument: documentId)"))
        XCTAssertFalse(source.contains("listEntitiesForDocument(documentId: documentId)"))
        XCTAssertFalse(source.contains("listInspectorEntitiesForDocument"))
        XCTAssertTrue(storeSource.contains("listInspectorEntitiesForDocument"))
        XCTAssertFalse(storeSource.contains("listEntitiesForDocument(documentId: documentId)"))
    }

    func testInspectorEntitiesTabDistinguishesLoadedButHiddenEntities() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )

        XCTAssertTrue(source.contains("Loaded \\(entityStore.entities.count) entities, but the current filter hides every kind."))
        XCTAssertTrue(source.contains("Loaded \\(entityStore.entities.count) entities, but none mapped into a visible section."))
    }

    func testInspectorListRowsUseFullRowHitTargets() throws {
        let entitiesSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )
        let artifactSource = try Self.appSource("Views/Library/Inspector/ArtifactListView.swift")
        let citationSource = try Self.appSource("Views/Library/Inspector/CitationListView.swift")
        let annotationSource = try Self.appSource("Views/Library/Inspector/AnnotationListView.swift")

        XCTAssertTrue(entitiesSource.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(entitiesSource.contains(".tag(entity.stableInspectorId)"))
        XCTAssertTrue(artifactSource.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(citationSource.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(annotationSource.contains(".contentShape(Rectangle())"))
    }

    func testInspectorEntitySelectionReducerPlainClickReplacesSelection() {
        let result = InspectorEntityBulkSelection.reduceTap(
            tappedId: "b",
            orderedIds: ["a", "b", "c"],
            selection: ["a", "c"],
            anchor: "a",
            modifiers: []
        )

        XCTAssertEqual(result.selection, ["b"])
        XCTAssertEqual(result.anchor, "b")
    }

    func testInspectorEntitySelectionReducerCommandClickTogglesSelection() {
        let result = InspectorEntityBulkSelection.reduceTap(
            tappedId: "b",
            orderedIds: ["a", "b", "c"],
            selection: ["a"],
            anchor: "a",
            modifiers: [.command]
        )

        XCTAssertEqual(result.selection, ["a", "b"])
        XCTAssertEqual(result.anchor, "b")
    }

    func testInspectorEntitySelectionReducerShiftClickBuildsRangeFromAnchor() {
        let result = InspectorEntityBulkSelection.reduceTap(
            tappedId: "d",
            orderedIds: ["a", "b", "c", "d"],
            selection: ["a"],
            anchor: "b",
            modifiers: [.shift]
        )

        XCTAssertEqual(result.selection, ["b", "c", "d"])
        XCTAssertEqual(result.anchor, "b")
    }

    func testInspectorEntitySelectionReducerCommandShiftUnionsRange() {
        let result = InspectorEntityBulkSelection.reduceTap(
            tappedId: "d",
            orderedIds: ["a", "b", "c", "d"],
            selection: ["a"],
            anchor: "b",
            modifiers: [.shift, .command]
        )

        XCTAssertEqual(result.selection, ["a", "b", "c", "d"])
        XCTAssertEqual(result.anchor, "b")
    }

    func testLibraryWideSuppressRulesDeduplicateCanonicalNames() {
        let entities = [
            Components.Schemas.KnowledgeEntity(
                id: "entity-1",
                canonicalName: "Ada Lovelace",
                entityType: .person,
                aliases: nil,
                description: nil,
                language: nil,
                metadata: nil,
                mergedIntoId: nil
            ),
            Components.Schemas.KnowledgeEntity(
                id: "entity-2",
                canonicalName: "ada lovelace",
                entityType: .person,
                aliases: nil,
                description: nil,
                language: nil,
                metadata: nil,
                mergedIntoId: nil
            )
        ]

        let rules = InspectorEntityBulkSelection.libraryWideSuppressRules(for: entities)

        XCTAssertEqual(rules.count, 1)
        XCTAssertEqual(rules.first?.ruleType, .suppress)
        XCTAssertEqual(rules.first?.matchCanonicalName, "Ada Lovelace")
        XCTAssertEqual(rules.first?.reason, "Bulk suppress from inspector")
    }

    func testInspectorEntityMergePlanPrefersHighestCorroborationCount() {
        var lowest = makeKnowledgeEntity(id: "entity-1", name: "Andagoya", type: .location)
        lowest.corroborationCount = 2

        var highest = makeKnowledgeEntity(id: "entity-2", name: "Andagóya", type: .location)
        highest.corroborationCount = 5

        var middle = makeKnowledgeEntity(id: "entity-3", name: "the Andagoya district", type: .location)
        middle.corroborationCount = 4

        let plan = InspectorEntityBulkSelection.mergePlan(for: [lowest, highest, middle])

        XCTAssertEqual(plan?.survivorId, "entity-2")
        XCTAssertEqual(plan?.survivorName, "Andagóya")
        XCTAssertEqual(plan?.absorbedEntityIds.sorted(), ["entity-1", "entity-3"])
        XCTAssertEqual(plan?.entityCount, 3)
    }

    func testInspectorEntityMergePlanBreaksTiesByLongestNameThenLexical() {
        var longest = makeKnowledgeEntity(id: "entity-1", name: "the Andagoya district", type: .location)
        longest.corroborationCount = 3

        var shorter = makeKnowledgeEntity(id: "entity-2", name: "Andagoya", type: .location)
        shorter.corroborationCount = 3

        let longestWinner = InspectorEntityBulkSelection.mergePlan(for: [shorter, longest])
        XCTAssertEqual(longestWinner?.survivorId, "entity-1")

        var lexicalA = makeKnowledgeEntity(id: "entity-3", name: "Andagoya", type: .location)
        lexicalA.corroborationCount = 3

        var lexicalB = makeKnowledgeEntity(id: "entity-4", name: "Andagóya", type: .location)
        lexicalB.corroborationCount = 3

        let lexicalWinner = InspectorEntityBulkSelection.mergePlan(for: [lexicalB, lexicalA])
        XCTAssertEqual(lexicalWinner?.survivorId, "entity-3")
        XCTAssertEqual(lexicalWinner?.survivorName, "Andagoya")
    }

    func testInspectorEntityMergePlanRejectsMixedKinds() {
        let person = makeKnowledgeEntity(id: "entity-1", name: "Andagoya", type: .person)
        let place = makeKnowledgeEntity(id: "entity-2", name: "Andagoya", type: .location)

        XCTAssertNil(InspectorEntityBulkSelection.mergePlan(for: [person, place]))
    }

    func testInspectorEntityMergePlanHonorsChosenSurvivor() {
        // The user can override the heuristic and merge INTO a chosen entity (#2499).
        var recommended = makeKnowledgeEntity(id: "entity-1", name: "Andagóya", type: .location)
        recommended.corroborationCount = 9  // would win the heuristic

        var chosen = makeKnowledgeEntity(id: "entity-2", name: "Andagoya", type: .location)
        chosen.corroborationCount = 1

        // Sanity: heuristic prefers entity-1.
        XCTAssertEqual(
            InspectorEntityBulkSelection.mergePlan(for: [recommended, chosen])?.survivorId,
            "entity-1"
        )

        // Chosen-survivor plan folds the (higher-corroborated) recommended INTO the pick.
        let plan = InspectorEntityBulkSelection.mergePlan(
            for: [recommended, chosen], survivorId: "entity-2"
        )
        XCTAssertEqual(plan?.survivorId, "entity-2")
        XCTAssertEqual(plan?.survivorName, "Andagoya")
        XCTAssertEqual(plan?.absorbedEntityIds, ["entity-1"])
        XCTAssertEqual(plan?.entityCount, 2)

        // A survivorId not in the set yields no plan.
        XCTAssertNil(InspectorEntityBulkSelection.mergePlan(
            for: [recommended, chosen], survivorId: "entity-404"
        ))
    }

    func testInspectorEntitiesTabUsesGeneratedBulkCurationOnly() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )
        let serviceSource = try Self.appSource("Services/ArtifactServiceGenerated.swift")
        // After the EntityStore migration, bulk curation calls live in EntityStore, not the view.
        let storeSource = try Self.appSource("Models/EntityStore.swift")

        XCTAssertTrue(storeSource.contains("batchSetEntityCurationState"))
        XCTAssertTrue(storeSource.contains("batchCreateEntityRules"))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URLRequest"))
        XCTAssertFalse(source.contains("URL(string:"))
        XCTAssertTrue(serviceSource.contains("batchSetEntityCurationStateApiKgEntitiesBatchCurationPatch"))
    }

    func testInspectorDeleteActionsUseGeneratedEntityAndClaimClients() throws {
        let entitiesSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift"
        )
        let claimsSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift"
        )
        let rowSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntityKindRow.swift"
        )
        let serviceSource = try Self.appSource("Services/ArtifactServiceGenerated.swift")

        // deleteEntity now goes through EntityStore; the view still owns the delete button UI.
        let storeSource = try Self.appSource("Models/EntityStore.swift")
        XCTAssertTrue(entitiesSource.contains("deleteActionButton(targetEntities: selectedEntities)"))
        XCTAssertTrue(entitiesSource.contains("Button(\"Delete…\", role: .destructive)"))
        XCTAssertTrue(storeSource.contains("try await entityService.deleteEntity(entityId)"))
        XCTAssertTrue(claimsSource.contains("deleteActionButton(targetClaims: selectedClaims)"))
        XCTAssertTrue(claimsSource.contains("requestClaimDeleteAction: requestDeleteAction(for:)"))
        XCTAssertTrue(claimsSource.contains("try await entityService.deleteClaim(claimId)"))
        XCTAssertTrue(rowSource.contains("Button(\"Delete…\", role: .destructive)"))
        XCTAssertTrue(rowSource.contains("requestClaimDeleteAction(targetClaims)"))
        XCTAssertFalse(entitiesSource.contains("URLSession"))
        XCTAssertFalse(claimsSource.contains("URLSession"))
        XCTAssertTrue(serviceSource.contains("deleteEntityApiEntitiesEntityIdDelete"))
        XCTAssertTrue(serviceSource.contains("deleteClaimApiClaimsClaimIdDelete"))
    }

    func testClaimLibraryWideSuppressRulesDeduplicateTriples() {
        let claims = [
            makeKnowledgeClaim(
                id: "claim-1",
                subject: "Andagoya",
                predicate: "is",
                object: "a place"
            ),
            makeKnowledgeClaim(
                id: "claim-2",
                subject: "andagoya",
                predicate: "is",
                object: "a place"
            )
        ]

        let rules = InspectorClaimBulkSelection.libraryWideSuppressRules(for: claims)

        XCTAssertEqual(rules.count, 1)
        XCTAssertEqual(rules.first?.action, .disable)
        XCTAssertEqual(rules.first?.matchSubjectName, "Andagoya")
        XCTAssertEqual(rules.first?.matchPredicateVerb, "is")
        XCTAssertEqual(rules.first?.matchObjectPhrase, "a place")
        XCTAssertEqual(rules.first?.reason, "Bulk suppress from inspector")
    }

    func testInspectorClaimMergePlanPrefersHighestCorroborationCountThenSupport() {
        var lower = makeKnowledgeClaim(
            id: "claim-1",
            subject: "Andagoya",
            predicate: "served as",
            object: "alcalde"
        )
        lower.corroborationCount = 2
        lower.weightedCorroborationCount = 2.0

        var highest = makeKnowledgeClaim(
            id: "claim-2",
            subject: "Andagóya",
            predicate: "served as",
            object: "alcalde mayor"
        )
        highest.corroborationCount = 5
        highest.weightedCorroborationCount = 5.0

        var middle = makeKnowledgeClaim(
            id: "claim-3",
            subject: "the Andagoya district",
            predicate: "served as",
            object: "district seat"
        )
        middle.corroborationCount = 4
        middle.weightedCorroborationCount = 4.0

        let plan = InspectorClaimBulkSelection.mergePlan(for: [lower, highest, middle])

        XCTAssertEqual(plan?.survivorId, "claim-2")
        XCTAssertEqual(plan?.survivorName, "Andagóya served as alcalde mayor")
        XCTAssertEqual(plan?.absorbedClaimIds.sorted(), ["claim-1", "claim-3"])
        XCTAssertEqual(plan?.claimCount, 3)
    }

    func testInspectorClaimMergePlanHonorsChosenSurvivor() {
        // The user can override the heuristic and merge INTO a chosen claim (#2499).
        var recommended = makeKnowledgeClaim(
            id: "claim-1", subject: "Andagóya", predicate: "served as", object: "alcalde mayor"
        )
        recommended.corroborationCount = 9  // would win the heuristic

        var chosen = makeKnowledgeClaim(
            id: "claim-2", subject: "Andagoya", predicate: "served as", object: "alcalde"
        )
        chosen.corroborationCount = 1

        // Sanity: heuristic prefers claim-1.
        XCTAssertEqual(
            InspectorClaimBulkSelection.mergePlan(for: [recommended, chosen])?.survivorId,
            "claim-1"
        )

        let plan = InspectorClaimBulkSelection.mergePlan(
            for: [recommended, chosen], survivorId: "claim-2"
        )
        XCTAssertEqual(plan?.survivorId, "claim-2")
        XCTAssertEqual(plan?.survivorName, "Andagoya served as alcalde")
        XCTAssertEqual(plan?.absorbedClaimIds, ["claim-1"])
        XCTAssertEqual(plan?.claimCount, 2)

        // A survivorId not in the set yields no plan.
        XCTAssertNil(InspectorClaimBulkSelection.mergePlan(
            for: [recommended, chosen], survivorId: "claim-404"
        ))
    }

    func testInspectorClaimMergePlanBreaksTiesByWeightedSupportThenLexical() {
        var lowerWeighted = makeKnowledgeClaim(
            id: "claim-1",
            subject: "Andagoya",
            predicate: "is",
            object: "a district"
        )
        lowerWeighted.corroborationCount = 3
        lowerWeighted.weightedCorroborationCount = 3.2

        var higherWeighted = makeKnowledgeClaim(
            id: "claim-2",
            subject: "Andagóya",
            predicate: "is",
            object: "a district"
        )
        higherWeighted.corroborationCount = 3
        higherWeighted.weightedCorroborationCount = 3.8

        let weightedWinner = InspectorClaimBulkSelection.mergePlan(
            for: [lowerWeighted, higherWeighted]
        )
        XCTAssertEqual(weightedWinner?.survivorId, "claim-2")

        var lexicalA = makeKnowledgeClaim(
            id: "claim-3",
            subject: "Andagoya",
            predicate: "is",
            object: "a district"
        )
        lexicalA.corroborationCount = 3
        lexicalA.weightedCorroborationCount = 3.0

        var lexicalB = makeKnowledgeClaim(
            id: "claim-4",
            subject: "Andagóya",
            predicate: "is",
            object: "a district"
        )
        lexicalB.corroborationCount = 3
        lexicalB.weightedCorroborationCount = 3.0

        let lexicalWinner = InspectorClaimBulkSelection.mergePlan(for: [lexicalB, lexicalA])
        XCTAssertEqual(lexicalWinner?.survivorId, "claim-3")
        XCTAssertEqual(lexicalWinner?.survivorName, "Andagoya is a district")
    }

    func testInspectorClaimMergePlanRejectsMergedClaims() {
        var canonical = makeKnowledgeClaim(
            id: "claim-1",
            subject: "Andagoya",
            predicate: "is",
            object: "a place"
        )
        canonical.mergedIntoId = nil

        var absorbed = makeKnowledgeClaim(
            id: "claim-2",
            subject: "andagoya",
            predicate: "is",
            object: "a place"
        )
        absorbed.mergedIntoId = "claim-1"

        XCTAssertNil(InspectorClaimBulkSelection.mergePlan(for: [canonical, absorbed]))
    }

    func testKnowledgeGraphInspectorSectionUsesGeneratedClaimBulkCurationOnly() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift"
        )
        let rowSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntityKindRow.swift"
        )
        let serviceSource = try Self.appSource("Services/ArtifactServiceGenerated.swift")

        XCTAssertTrue(source.contains("batchSetClaimCurationState"))
        XCTAssertTrue(source.contains("batchCreateClaimRules"))
        XCTAssertTrue(source.contains("kgCurationService.mergeClaims"))
        XCTAssertTrue(source.contains("claimMergeActionMenu(targetClaims: selectedClaims, menuTitle: \"Merge\")"))
        XCTAssertTrue(source.contains("Menu(\"Prune trivial\")"))
        XCTAssertTrue(source.contains("kgCurationService.pruneTrivialClaims"))
        XCTAssertTrue(source.contains("// TODO(#1689): claim unmerge UI"))
        XCTAssertTrue(rowSource.contains("Menu(\"Suppress\")"))
        // #2499: the merge context action is now a destination-picker submenu
        // (one "Into …" button per candidate) instead of a single button.
        XCTAssertTrue(rowSource.contains("Menu(\"Merge\")"))
        XCTAssertTrue(rowSource.contains("(Recommended)"))
        XCTAssertTrue(rowSource.contains("Menu(\"Prune trivial\")"))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URLRequest"))
        XCTAssertFalse(source.contains("URL(string:"))
        XCTAssertTrue(serviceSource.contains("batchSetClaimCurationStateApiKgClaimsBatchCurationPatch"))
        XCTAssertTrue(serviceSource.contains("mergeClaimsApiKgClaimsMergePost"))
        XCTAssertTrue(serviceSource.contains("unmergeClaimsApiKgClaimsUnmergePost"))
        XCTAssertTrue(serviceSource.contains("pruneTrivialClaimsApiKgClaimsPruneTrivialPost"))
    }

    func testPruneTrivialClaimsRequestUsesDocumentScope() {
        let request = KGCurationServiceGenerated.makePruneTrivialClaimsRequest(
            scope: .document(documentId: "page-1")
        )

        XCTAssertEqual(request.documentId, "page-1")
        XCTAssertNil(request.folderId)
        XCTAssertFalse(request.libraryWide ?? false)
        XCTAssertEqual(request.reason, "Prune trivial is-a copula claims")
        XCTAssertEqual(request.createdBy, "human")
    }

    func testPruneTrivialClaimsRequestUsesFolderScope() {
        let request = KGCurationServiceGenerated.makePruneTrivialClaimsRequest(
            scope: .folder(folderId: "folder-1")
        )

        XCTAssertNil(request.documentId)
        XCTAssertEqual(request.folderId, "folder-1")
        XCTAssertFalse(request.libraryWide ?? false)
    }

    func testPruneTrivialClaimsRequestUsesLibraryWideScope() {
        let request = KGCurationServiceGenerated.makePruneTrivialClaimsRequest(
            scope: .libraryWide
        )

        XCTAssertNil(request.documentId)
        XCTAssertNil(request.folderId)
        XCTAssertTrue(request.libraryWide ?? false)
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

    /// #2697: the inspector scope must DEFAULT to the item's own records so a
    /// folder/PDF doesn't mix its children's entities/attributes in. The flag
    /// lives in two views under one @AppStorage key — both must declare the same
    /// `false` default, or the key's registered default is ambiguous.
    func testInspectorScopeDefaultsToThisItemOnly() throws {
        let kgSection = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift"
        )
        let attributesStrip = try Self.appSource("Views/Library/DisplayAttributesStrip.swift")
        let declaration =
            #"@AppStorage("inspector.scope.includeChildren") private var includeChildren: Bool = false"#
        XCTAssertTrue(
            kgSection.contains(declaration),
            "KG section must default the inspector scope to this-item-only (#2697)"
        )
        XCTAssertTrue(
            attributesStrip.contains(declaration),
            "Attributes strip must default the inspector scope to this-item-only (#2697)"
        )
        // Guard the invariant: no declaration of this key may default to true.
        let staleDefault =
            #"@AppStorage("inspector.scope.includeChildren") private var includeChildren: Bool = true"#
        XCTAssertFalse(kgSection.contains(staleDefault))
        XCTAssertFalse(attributesStrip.contains(staleDefault))
    }

    /// #2696: the Content-pane top attributes should surface interesting
    /// artefacts as they're added — the entities summary defaults ON and the
    /// row is gated on a non-zero count so it appears only when the page has
    /// entities.
    func testAttributesStripSurfacesEntitiesByDefault() throws {
        let strip = try Self.appSource("Views/Library/DisplayAttributesStrip.swift")
        XCTAssertTrue(
            strip.contains(#"@AppStorage("inspector.attributeStrip.kg") private var shownKGRaw: String = "entities""#),
            "KG summaries must default to surfacing entities (#2696)"
        )
        XCTAssertTrue(
            strip.contains("$0 != .entities || (entityCount ?? 0) > 0"),
            "the entities row must be gated on a non-zero count so it appears as added (#2696)"
        )
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

    private func makeKnowledgeEntity(
        id: String,
        name: String,
        type: Components.Schemas.EntityTypeOutput
    ) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(
            id: id,
            canonicalName: name,
            entityType: type,
            aliases: nil,
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil
        )
    }
}

private func makeKnowledgeClaim(
    id: String,
    subject: String,
    predicate: String,
    object: String
) -> Components.Schemas.KnowledgeClaim {
    Components.Schemas.KnowledgeClaim(
        id: id,
        text: "\(subject) \(predicate) \(object)",
        subjectCanonical: subject,
        predicateVerb: predicate,
        objectPhrase: object
    )
}
// swiftlint:enable file_length type_body_length
