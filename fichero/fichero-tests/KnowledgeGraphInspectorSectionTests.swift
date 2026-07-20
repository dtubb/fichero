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

    private static func entityStoreSource() throws -> String {
        try [
            appSource("Models/EntityStore.swift"),
            appSource("Models/EntityStore+Loading.swift"),
            appSource("Models/EntityStore+Mutations.swift"),
        ].joined(separator: "\n")
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
        let source = try Self.appSource("Views/Reader/Knowledge/DocumentKGWebPane.swift")
            + Self.appSource("Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift")
            + Self.appSource("Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift")
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
        // #4024: DocumentInspectorEntitiesTab was split; the store-loading call
        // now lives in the +Scope.swift sibling, not the core file.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Scope.swift"
        )
        // After the EntityStore migration, the view calls the store; the store calls the endpoint.
        let storeSource = try Self.entityStoreSource()

        XCTAssertTrue(source.contains("entityStore.loadEntities(forDocument: documentId, force: force)"))
        XCTAssertFalse(source.contains("listEntitiesForDocument(documentId: documentId)"))
        XCTAssertFalse(source.contains("listInspectorEntitiesForDocument"))
        XCTAssertTrue(storeSource.contains("listInspectorEntitiesForDocument"))
        XCTAssertFalse(storeSource.contains("listEntitiesForDocument(documentId: documentId)"))
    }

    func testInspectorEntitiesTabDistinguishesLoadedButHiddenEntities() throws {
        // #4024: the empty-state copy now lives in the +Rows.swift sibling.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift"
        )

        XCTAssertTrue(source.contains("Loaded \\(scopedEntities.count) entities, but the current filter hides every kind."))
        XCTAssertTrue(source.contains("Loaded \\(scopedEntities.count) entities, but none mapped into a visible section."))
    }

    func testInspectorListRowsUseFullRowHitTargets() throws {
        // #4024: the row modifiers moved into the +Rows.swift sibling.
        let entitiesSource = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift"
        )
        let inspectorSource = try Self.appSource("Views/Inspector/Document/DocumentInspector.swift")
        let artifactSource = try Self.appSource("Views/Inspector/Artifacts/ArtifactListView.swift")
        let citationSource = try Self.appSource("Views/Inspector/Knowledge/Citations/CitationListView.swift")
        let annotationSource = try Self.appSource("Views/Inspector/Notes/Annotations/AnnotationListView.swift")

        XCTAssertTrue(inspectorSource.contains("func inspectorListRowTarget()"))
        XCTAssertTrue(entitiesSource.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(entitiesSource.contains(".tag(entity.stableInspectorId)"))
        XCTAssertTrue(artifactSource.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(citationSource.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(annotationSource.contains(".inspectorListRowTarget()"))
    }

    func testDocumentInspectorArtifactPanelsRouteSelectionIntoArtifactInspector() throws {
        let source = try Self.appSource("Views/Inspector/Source/DocumentInspectorContentV2.swift")

        XCTAssertTrue(source.contains("FocusedArtifact.shared.select("))
        XCTAssertTrue(source.contains("documentId: document.id"))
        XCTAssertTrue(source.contains(".onTapGesture"))
        XCTAssertTrue(source.contains("@Environment(ArtifactStore.self)"))
        XCTAssertFalse(source.contains("@Environment(ArtifactService.self)"))
        XCTAssertTrue(source.contains("await artifactStore.setScope("))
        XCTAssertTrue(source.contains("await artifactStore.delete([artifact])"))
        XCTAssertTrue(source.contains("try await artifactStore.update("))
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
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        )
        // #4024: the batch-curation generated call moved out of ArtifactService
        // into the dedicated KGCurationService.
        let serviceSource = try Self.appSource("Services/KGCurationService.swift")
        // After the EntityStore migration, bulk curation calls live in EntityStore, not the view.
        let storeSource = try Self.entityStoreSource()

        XCTAssertTrue(storeSource.contains("batchSetEntityCurationState"))
        XCTAssertTrue(storeSource.contains("batchCreateEntityRules"))
        XCTAssertFalse(source.contains("URLSession"))
        XCTAssertFalse(source.contains("URLRequest"))
        XCTAssertFalse(source.contains("URL(string:"))
        XCTAssertTrue(serviceSource.contains("batchSetEntityCurationStateApiKgEntitiesBatchCurationPatch"))
    }

    func testInspectorEntitiesTabSupportsOwnProcessDragDropAndTypeChange() throws {
        // #4024: drag/drop modifiers moved to +Rows.swift; merge/reclassify
        // plan assignment moved to +Actions.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Actions.swift"
        )
        let sharedSource = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraphSupport.swift"
        )
        let storeSource = try Self.entityStoreSource()

        XCTAssertTrue(source.contains(".draggable(InspectorEntityDragID(id: entity.stableInspectorId, text: entity.canonicalName))"))
        XCTAssertTrue(source.contains(".dropDestination("))
        XCTAssertTrue(source.contains("pendingMergePlan = plan"))
        XCTAssertTrue(source.contains("pendingReclassifyPlan = PendingEntityReclassifyPlan("))
        XCTAssertTrue(sharedSource.contains("var apiTypeId: String?"))
        XCTAssertTrue(storeSource.contains("func reclassify("))
    }

    func testInspectorEntityMergeKeepsFocusOnSurvivorAfterReload() throws {
        // #4024: the post-merge focus-restore logic moved to +Actions.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Actions.swift"
        )

        XCTAssertTrue(source.contains("restoreSelectionAfterEntityRefresh(entityId: plan.survivorId)"))
        XCTAssertTrue(source.contains("entitySelection = [entity.stableInspectorId]"))
        XCTAssertTrue(source.contains("onEntitySelect?(entityId)"))
    }

    func testInspectorEntityReclassifyKeepsFocusAfterDropRefresh() throws {
        // #4024: the post-reclassify focus-restore logic moved to +Actions.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Actions.swift"
        )

        XCTAssertTrue(source.contains("restoreSelectionAfterEntityRefresh(entityId: plan.entityId)"))
    }

    func testInspectorEntitiesTabUsesSharedBottomMiniToolbarForSelectionActions() throws {
        // #4024: entitiesMiniToolbar and its contents moved to +Rows.swift.
        // NOTE: the moved declaration is `var entitiesMiniToolbar` (no `private`)
        // because it must be visible from the core file's body across the file
        // split (Swift `private` is file-scoped). The literal "private var
        // entitiesMiniToolbar…" assertion below is updated below (incidental `private` dropped) —
        // resolved in #4024 by dropping the incidental `private` (split forces internal); behavioral assertion unchanged.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift"
        )

        XCTAssertTrue(source.contains("var entitiesMiniToolbar: some View"))
        XCTAssertTrue(source.contains("InspectorBottomMiniToolbar(statusText: entitiesToolbarStatusText)"))
        XCTAssertTrue(source.contains("if entitySelection.count > 1 {"))
        XCTAssertTrue(source.contains("mergeActionMenu(targetEntities: selectedEntities, menuTitle: \"Merge\")"))
        XCTAssertTrue(source.contains("deleteActionButton(targetEntities: selectedEntities)"))
    }

    func testInspectorEntitiesTabReadsPerDocumentEntityStoreBuckets() throws {
        // #4024: the per-document bucket reads moved to +Scope.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Scope.swift"
        )
        let storeSource = try Self.entityStoreSource()

        XCTAssertTrue(source.contains("entityStore.entities(forDocument: documentId)"))
        XCTAssertTrue(source.contains("entityStore.loadError(forDocument: documentId)"))
        XCTAssertTrue(source.contains("entityStore.isLoading(forDocument: documentId)"))
        XCTAssertTrue(storeSource.contains("var entitiesByDocumentId"))
        XCTAssertTrue(storeSource.contains("func entities(forDocument documentId: String)"))
    }

    func testOntologyBrowserLibraryListUsesEntityStoreAndClaimStoreActions() throws {
        let browserSource = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser.swift"
        )
        let listSource = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+List.swift"
        )
        let triageSource = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ContradictionTriageSheet.swift"
        )
        let storeSource = try Self.entityStoreSource()

        XCTAssertTrue(browserSource.contains("@Environment(EntityStore.self) var entityStore"))
        XCTAssertTrue(browserSource.contains("entityStore.libraryEntities"))
        XCTAssertTrue(listSource.contains("try await entityStore.delete(entityIds: [entityId])"))
        XCTAssertTrue(listSource.contains("await entityStore.loadEntities(limit: Self.entityListLimit)"))
        XCTAssertTrue(listSource.contains("await entityStore.loadEntities(query: searchText"))
        XCTAssertFalse(listSource.contains("LibraryManager.shared.globalLibrary!"))
        XCTAssertTrue(storeSource.contains("entityService.listEntities(query: searchQuery, limit: limit)"))
        XCTAssertTrue(storeSource.contains("entityService.fetchClaimCounts()"))
        XCTAssertTrue(triageSource.contains("@Environment(ClaimStore.self) private var claimStore"))
        XCTAssertTrue(triageSource.contains("try await claimStore.patch(claimId: claimId, curationState: state)"))
        XCTAssertFalse(triageSource.contains("library.entityService.patchClaim"))
    }

    func testKnowledgeGraphTextDigestUsesStableEntryIds() throws {
        // #4024: TextDigestEntry moved to +Grouping.swift, the ForEach that
        // renders it moved to +Views.swift.
        // NOTE: TextDigestEntry is declared `struct` (no `private`) in
        // +Grouping.swift because it must be visible from +Views.swift and the
        // core file's @State across the file split (Swift `private` is
        // file-scoped) — see the "Promoted `private` → internal" comment there.
        // The literal "private struct TextDigestEntry…" assertion below will
        // still fail post-repoint — resolved (#4024): dropped incidental `private`; split forces internal; behavioral assertion unchanged.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Grouping.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Views.swift"
        )

        XCTAssertTrue(source.contains("struct TextDigestEntry: Identifiable"))
        XCTAssertTrue(source.contains("id: item.id"))
        XCTAssertTrue(source.contains("ForEach(entries) { entry in"))
        XCTAssertFalse(source.contains("ForEach(entries, id: \\.displayName)"))
    }

    func testInspectorDeleteActionsUseGeneratedEntityAndClaimClients() throws {
        // #4024: delete-button UI and wiring split across siblings; the
        // generated client calls moved out of ArtifactService into
        // EntityService+ClaimEntityCRUD.
        let entitiesSource = try Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Menus.swift"
        )
        let claimsSource = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Toolbar.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Views.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Actions.swift"
        )
        let rowSource = try Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow+Actions.swift"
        )
        let serviceSource = try Self.appSource("Services/EntityService+ClaimEntityCRUD.swift")

        // deleteEntity now goes through EntityStore; the view still owns the delete button UI.
        let storeSource = try Self.entityStoreSource()
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
        // #4024: bulk-curation/merge/prune wiring split into +Actions.swift and
        // +Toolbar.swift; the row's context-menu wiring moved to
        // EntityKindRow+Actions.swift; the generated client calls moved out of
        // ArtifactService into the dedicated KGCurationService.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Actions.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Toolbar.swift"
        )
        let rowSource = try Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow+Actions.swift"
        )
        let serviceSource = try Self.appSource("Services/KGCurationService.swift")

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
        let request = KGCurationService.makePruneTrivialClaimsRequest(
            scope: .document(documentId: "page-1")
        )

        XCTAssertEqual(request.documentId, "page-1")
        XCTAssertNil(request.folderId)
        XCTAssertFalse(request.libraryWide ?? false)
        XCTAssertEqual(request.reason, "Prune trivial is-a copula claims")
        XCTAssertEqual(request.createdBy, "human")
    }

    func testPruneTrivialClaimsRequestUsesFolderScope() {
        let request = KGCurationService.makePruneTrivialClaimsRequest(
            scope: .folder(folderId: "folder-1")
        )

        XCTAssertNil(request.documentId)
        XCTAssertEqual(request.folderId, "folder-1")
        XCTAssertFalse(request.libraryWide ?? false)
    }

    func testPruneTrivialClaimsRequestUsesLibraryWideScope() {
        let request = KGCurationService.makePruneTrivialClaimsRequest(
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
        // #4024: both declarations still live in their respective core files
        // post-split (no path change needed). NOTE: neither declares `private`
        // any more — the split forced `includeChildren` to at least internal
        // visibility so sibling extension files (e.g. DisplayAttributesStrip+*)
        // can read it (Swift `private` is file-scoped). The `declaration`
        // literal below still requires `private`, so this assertion will still
        // fail post-repoint — resolved (#4024): dropped incidental `private`; split forces internal; behavioral assertion unchanged.
        let kgSection = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        )
        let attributesStrip = try Self.appSource("Views/Inspector/DisplayAttributesStrip.swift")
        let declaration =
            #"@AppStorage("inspector.scope.includeChildren") var includeChildren: Bool = false"#
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
            #"@AppStorage("inspector.scope.includeChildren") var includeChildren: Bool = true"#
        XCTAssertFalse(kgSection.contains(staleDefault))
        XCTAssertFalse(attributesStrip.contains(staleDefault))
    }

    /// #2696: the Content-pane top attributes should surface interesting
    /// artefacts as they're added — the entities summary defaults ON and the
    /// row is gated on a non-zero count so it appears only when the page has
    /// entities.
    func testAttributesStripSurfacesEntitiesByDefault() throws {
        // #4024: the @AppStorage declaration stays in the core file; the
        // gating filter moved to +Attributes.swift. NOTE: the declaration is
        // `var shownKGRaw` (no `private`) because it must be readable from
        // sibling extension files (e.g. +Attributes.swift) across the file
        // split (Swift `private` is file-scoped). The literal
        // "…private var shownKGRaw…" assertion below still requires `private`,
        // so the incidental `private` was dropped (#4024); split forces internal; behavioral assertion unchanged.
        let strip = try Self.appSource(
            "Views/Inspector/DisplayAttributesStrip.swift"
        ) + Self.appSource(
            "Views/Inspector/DisplayAttributesStrip+Attributes.swift"
        )
        XCTAssertTrue(
            strip.contains(#"@AppStorage("inspector.attributeStrip.kg") var shownKGRaw: String = "entities""#),
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

    // MARK: - Source provenance anchor (#3449, item 12)

    func testKGClaimBuildsSourceNavigationRequestWhenSourced() {
        let claim = Components.Schemas.KnowledgeClaim(
            id: "claim-1",
            text: "Ada wrote the notes",
            sourceDocumentId: "doc-9",
            sourcePageLabel: "page 4",
            sourceExcerpt: "the verbatim quote"
        )

        let request = ClaimSummaryCard.openClaimSourceRequest(for: claim)

        XCTAssertNotNil(request, "A claim with a source document should yield a provenance anchor")
        XCTAssertEqual(request?.documentId, "doc-9")
        XCTAssertEqual(request?.pageLabel, "page 4")
        XCTAssertEqual(request?.claimText, "the verbatim quote")
        XCTAssertEqual(request?.claimId, "claim-1")
    }

    func testKGClaimWithoutSourceDocumentHasNoProvenanceAnchor() {
        // No sourceDocumentId → no anchor, so the row shows no provenance popover
        // (rather than a broken empty one).
        let claim = Components.Schemas.KnowledgeClaim(
            id: "claim-2",
            text: "Unsourced assertion"
        )

        XCTAssertNil(ClaimSummaryCard.openClaimSourceRequest(for: claim))
    }

    // MARK: - Inline S/V/O editing (#3463)

    func testKGClaimRowEditsSVOInlineNotInASheet() throws {
        // #4024: the inline SVO editor wiring moved to +ClaimBlock.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift"
        )

        // "Edit S/V/O…" expands the row into the inline editor (reusing
        // InlineClaimEditor); the old EditClaimSheet presentation is gone.
        XCTAssertTrue(source.contains("InlineClaimEditor("))
        XCTAssertTrue(source.contains("inlineEditingClaimId"))
        XCTAssertFalse(source.contains("EditClaimSheet("))
    }

    // MARK: - Cross-target drag payload (#3425)

    func testInspectorEntityDragPayloadRoundTripsAcrossTargets() throws {
        // The structured JSON representation must survive serialization so the
        // entity drag carries its full identity across app targets/scenes.
        let payload = InspectorEntityDragID(id: "e-1", text: "Ada Lovelace")
        let data = try JSONEncoder().encode(payload)
        let decoded = try JSONDecoder().decode(InspectorEntityDragID.self, from: data)
        XCTAssertEqual(decoded.id, "e-1")
        XCTAssertEqual(decoded.text, "Ada Lovelace")
    }

    // MARK: - SPARQL console (#3298)

    func testSparqlConsoleUsesTypedQueryOpsThroughAStore() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Sheets.swift"
        )
        let storeSource = try Self.appSource("Models/KGQueryStore.swift")

        // The console routes the W3C query layer through KGQueryStore on the
        // typed generated ops — seeded from /examples, run via /query/sparql —
        // not a hand-rolled URL, and surfaces the truncation flag (#3298).
        XCTAssertTrue(storeSource.contains("final class KGQueryStore"))
        XCTAssertTrue(storeSource.contains("sparqlQueryApiKgQuerySparqlPost"))
        XCTAssertTrue(storeSource.contains("sparqlExamplesApiKgQueryExamplesGet"))
        XCTAssertTrue(source.contains("response.truncated"))
        XCTAssertFalse(source.contains("URLSession"))
    }

    // MARK: - OntologyBrowser store routing (#3300)

    func testOntologyBrowserEntityClaimsRouteThroughClaimStore() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Detail.swift"
        )

        // The entity-detail claims load goes through ClaimStore (observable data
        // layer), not a LibraryManager.shared singleton + per-doc
        // documentKnowledgeGraph fan-out (#3300).
        XCTAssertTrue(source.contains("claimStore.loadClaims(forEntity:"))
        XCTAssertFalse(source.contains("LibraryManager.shared.globalLibrary"))
        XCTAssertFalse(source.contains("documentKnowledgeGraph("))
    }

    // MARK: - Native List conversion (#3425, item 14)

    func testKGListModeUsesNativeListSelectionWithKindSections() throws {
        // #4024: the native List body and its modifiers moved to +Views.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Views.swift"
        )

        // List mode is a native List(selection:) so it gets arrow-key nav +
        // multi-select for free, grouped into per-kind Sections, with a
        // focus-on-single-selection seam replacing the old click reducer.
        XCTAssertTrue(source.contains("List(selection: $claimSelection)"))
        XCTAssertTrue(source.contains(".tag(item.claimId)"))
        XCTAssertTrue(source.contains("focusSingleSelectedClaim"))
        XCTAssertTrue(source.contains(".onChange(of: claimSelection)"))
    }

    func testKGListWiresSpaceKeySourceQuickLook() throws {
        // #4024: the space-key handling and quick-look popover moved to +Views.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Views.swift"
        )

        // Space on a selected claim opens the source quick-look popover, reusing
        // the shared SourceProvenanceCard (#3449 item-12 extension).
        XCTAssertTrue(source.contains(".onKeyPress(.space)"))
        XCTAssertTrue(source.contains("spaceQuickLookClaimId"))
        XCTAssertTrue(source.contains("SourceProvenanceCard("))
    }

    func testKGClaimRowDefersSingleClickSelectionToTheList() throws {
        // #4024: the double-click gesture wiring moved to +ClaimBlock.swift.
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow.swift"
        ) + Self.appSource(
            "Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift"
        )

        // The row no longer owns single-click selection (the List does); it keeps
        // the double-click-to-open gesture.
        XCTAssertFalse(source.contains(".onTapGesture"))
        XCTAssertTrue(source.contains("TapGesture(count: 2)"))
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
// MARK: - Entity reconciliation grouping (#3318)

@MainActor
final class EntityReconciliationTests: XCTestCase {
    func testParsesCandidatePairsFromEngineEnvelope() throws {
        // The /api/kg/entity-curation/candidates envelope: { items: [pairs], count }.
        let json = Data("""
        {"count": 2, "items": [
          {"entity_a_id": "a", "entity_a_name": "Pedro", "entity_b_id": "b",
           "entity_b_name": "Pedro de la Vega", "jaccard": 0.82, "shared_neighbors": 5,
           "entity_type": "person"},
          {"entity_a_id": "x", "entity_a_name": "x", "entity_b_id": "x",
           "entity_b_name": "x", "jaccard": 0.9}
        ]}
        """.utf8)
        let pairs = EntityStore.parseReconciliationCandidates(json)
        // The self-pair (a==b) is dropped; the real pair is parsed.
        XCTAssertEqual(pairs.count, 1)
        let pair = try XCTUnwrap(pairs.first)
        XCTAssertEqual(pair.entityAId, "a")
        XCTAssertEqual(pair.entityBName, "Pedro de la Vega")
        XCTAssertEqual(pair.jaccard, 0.82, accuracy: 0.001)
        XCTAssertEqual(pair.entityType, "person")
        XCTAssertEqual(pair.id, "a|b")
    }

    func testParsesEmptyOrMalformedEnvelopeToNoPairs() {
        XCTAssertTrue(EntityStore.parseReconciliationCandidates(Data("null".utf8)).isEmpty)
        XCTAssertTrue(EntityStore.parseReconciliationCandidates(Data("{\"count\":0,\"items\":[]}".utf8)).isEmpty)
    }

    func testScopeAvailabilityMatchesTheShippedScopes() {
        // Folder + Library ship now; cross-library (#3527) + external (#3528) are
        // deferred and must render disabled.
        XCTAssertTrue(EntityReconciliationScope.folder.isAvailable)
        XCTAssertTrue(EntityReconciliationScope.library.isAvailable)
        XCTAssertFalse(EntityReconciliationScope.crossLibrary.isAvailable)
        XCTAssertFalse(EntityReconciliationScope.external.isAvailable)
    }
}

// swiftlint:enable file_length type_body_length
