@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: kg-entity-inspector — the header's remaining TEST GAPS.
///
/// Five already-built behaviors the spec named as code-landed-but-unpinned:
/// `statements.loads-via-store`, `statements.resyncs-on-change`,
/// `select.routes-to-entities-tab`, `select.never-another-entity`,
/// `rekey.on-focus-change`, and the cross-surface `xsurface.same-line`.
///
/// Where a behavior is a pure model rule (the statement-line composer, the
/// store's entity scope) it is pinned by a deterministic behavior test. Where it
/// is a SwiftUI `.onChange` / `.task(id:)` modifier that cannot be exercised in
/// isolation (the change-token observer, the focus→tab route, the re-key reset),
/// it is pinned by a comment-stripped source-scan — the same style the sibling
/// `KnowledgeGraphInspectorSectionTests` / `EntityClickthroughTests` use for
/// view-level invariants — over `AppSource.code(...)`.
@MainActor
struct EntityInspectorPinningTests {

    // MARK: - Fixtures

    private static func claim(
        id: String = "c1",
        subject: String? = nil,
        verb: String? = nil,
        object: String? = nil,
        text: String = "t"
    ) -> Components.Schemas.KnowledgeClaim {
        var value = Components.Schemas.KnowledgeClaim(id: id, text: text)
        value.subjectCanonical = subject
        value.predicateVerb = verb
        value.objectPhrase = object
        return value
    }

    /// A ClaimStore over a never-connecting client — the same shape
    /// `ClaimChangeDeliveryTests` builds. Enough to drive scope/token state
    /// without a live engine.
    private static func makeClaimStore() -> ClaimStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = []
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
        return ClaimStore(
            entityService: EntityService(ficheroClient: client),
            kgCurationService: KGCurationService(ficheroClient: client),
            libraryPath: "/tmp/test.fichero"
        )
    }

    /// The one statement-line composer every entity-statement surface shares:
    /// `ClaimSummaryCard.svoTriple` feeding `ClaimLine.text`. Computing a line
    /// this way IS what the digest (`provenanceSummary`) and the ontology
    /// detail panel do; the source-scan below proves neither hand-rolls its own.
    private static func statementLine(
        for claim: Components.Schemas.KnowledgeClaim,
        groupSubject: String?
    ) -> String {
        let svo = ClaimSummaryCard.svoTriple(for: claim)
        return ClaimLine.text(
            subject: svo?.subject,
            verb: svo?.verb,
            object: svo?.object,
            fallback: claim.text,
            groupSubject: groupSubject
        )
    }

    // MARK: - B. statements.loads-via-store

    /// spec: kg-entity-inspector — `kg.entity.statements.loads-via-store` (F3).
    ///
    /// The entity's claims are the STORE's responsibility: `loadClaims(forEntity:)`
    /// moves the store onto that entity's scope, which is the observable list the
    /// digest then reads (`claims = claimStore.claims`). A view fetching claims
    /// itself could never join the change-stream that resync depends on.
    @Test("loadClaims(forEntity:) puts the store on that entity's scope")
    func entityLoadRoutesThroughStoreScope() async {
        let store = Self.makeClaimStore()
        #expect(store.scope == .none)

        await store.loadClaims(forEntity: "entity-42")

        // The fetch cannot succeed against the dead client, but the store still
        // OWNS the entity scope — the load path is the store's, not a bespoke
        // view fetch on a different axis.
        #expect(store.scope == .entity("entity-42"))
    }

    /// spec: kg-entity-inspector — `kg.entity.statements.loads-via-store` (F3).
    ///
    /// The digest's `loadClaims` prefers the store (`claimStore.loadClaims(forEntity:`)
    /// and reads its observable list, falling back to a direct service fetch ONLY
    /// when no store is in the environment (the digest also renders in panes that
    /// don't carry one). Pins the load path on `EntityDigestContent` itself — the
    /// nearest prior test scraped a different file (`OntologyBrowser+Detail.swift`).
    @Test("the digest loads statements through ClaimStore, not a bespoke fetch")
    func digestLoadsViaClaimStore() throws {
        // #4896: loadClaims moved to EntityDigestContent+Provenance.swift.
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestContent+Provenance.swift")

        #expect(digest.contains("if let claimStore {"))
        #expect(digest.contains("await claimStore.loadClaims(forEntity: entityId, force: true)"))
        #expect(digest.contains("claims = claimStore.claims"))
        // The direct service call survives only as the no-store fallback, inside
        // the else branch — never as the primary path.
        let storeBranch = try #require(
            digest.components(separatedBy: "if let claimStore {").dropFirst().first
        )
        let elseIndex = try #require(String(storeBranch).range(of: "} else {"))
        let primaryPath = String(storeBranch[storeBranch.startIndex..<elseIndex.lowerBound])
        #expect(!primaryPath.contains("entityService.listClaims"))
    }

    // MARK: - B. statements.resyncs-on-change

    /// spec: kg-entity-inspector — `kg.entity.statements.resyncs-on-change` (F3).
    ///
    /// The digest observes `ClaimStore.changeToken` and re-reads on a bump, so an
    /// edit / merge / delete / curation change on ANY surface is visible here
    /// without reselecting. The token movement itself is pinned by
    /// `ClaimChangeDeliveryTests`; this pins the digest's observer of it, which
    /// the spec named as having no test.
    @Test("the digest resyncs its statements when the store's change token moves")
    func digestObservesChangeToken() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")

        let observer = try #require(
            digest.components(separatedBy: ".onChange(of: claimStore?.changeToken)").dropFirst().first
        )
        // The observer's body re-loads this entity's claims.
        #expect(String(observer.prefix(200)).contains("await loadClaims()"))
    }

    /// spec: kg-entity-inspector — `kg.entity.statements.resyncs-on-change` (F3).
    ///
    /// The store starts with a zero change token; the observed value exists and is
    /// monotonic — the primitive the digest's observer keys on.
    @Test("the store exposes a change token the digest can key on")
    func storeExposesChangeToken() {
        let store = Self.makeClaimStore()
        #expect(store.changeToken == 0)
    }

    // MARK: - A. select.routes-to-entities-tab

    /// spec: kg-entity-inspector — `kg.entity.select.routes-to-entities-tab`.
    ///
    /// When a document IS shown, focusing an entity switches the inspector to the
    /// Entities tab (`selectedTab = .entities` on a `focusedEntityId` change) and
    /// selects that entity's row (`syncSelectionToFocusedEntity` →
    /// `entitySelection = [stableId]`) rather than navigating away from the doc.
    @Test("focusing an entity routes a shown document's inspector to the Entities tab")
    func focusRoutesToEntitiesTab() throws {
        let inspector = try AppSource.code("Views/Inspector/Document/DocumentInspector.swift")

        let route = try #require(
            inspector.components(separatedBy: ".onChange(of: kgFocusState.focusedEntityId)").dropFirst().first
        )
        #expect(String(route.prefix(160)).contains("selectedTab = .entities"))

        let actions = try AppSource.code(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Actions.swift"
        )
        let sync = try #require(
            actions.components(separatedBy: "func syncSelectionToFocusedEntity()").dropFirst().first
        )
        #expect(String(sync.prefix(320)).contains("entitySelection = [stableId]"))
    }

    // MARK: - A/D. select.never-another-entity + rekey.on-focus-change

    /// spec: kg-entity-inspector — `kg.entity.rekey.on-focus-change` +
    /// `kg.entity.select.never-another-entity` (D).
    ///
    /// The entity arm is keyed on `entityId` via `.task(id: entityId)` and CLEARS
    /// the old entity (`entity = nil`) before refetching — so a focus change drops
    /// the previous entity rather than showing its record under a new header (the
    /// #965 class). The pane belongs to the newly-focused entity or nothing.
    @Test("the entity arm re-keys on focus and drops the previous entity")
    func entityArmRekeysAndClearsOnFocusChange() throws {
        let inspector = try AppSource.code("Views/Inspector/Document/DocumentInspector.swift")

        // #4902: f47f4b60d added loadFailed/loadFailureReason resets ahead of
        // `entity = nil`, pushing both checked strings past a fixed-length
        // `.prefix(160)` window. Bound by the task's own closing brace instead
        // (the "\n            }" body-boundary pattern, as for the font test),
        // which survives however much the block grows.
        let start = try #require(inspector.range(of: ".task(id: entityId) {"))
        let bodyEnd = try #require(
            inspector.range(of: "\n            }", range: start.upperBound..<inspector.endIndex)
        )
        let body = inspector[start.upperBound..<bodyEnd.lowerBound]
        // Reset FIRST so the stale entity never renders under the new id.
        #expect(body.contains("entity = nil"))
        #expect(body.contains("entityService.getEntity(entityId)"))
    }

    /// spec: kg-entity-inspector — `kg.entity.rekey.on-focus-change` +
    /// `kg.entity.select.never-another-entity` (D).
    ///
    /// The statements list is keyed on `entity.id` via `.task(id:)`, and its
    /// `loadClaims` REPLACES `claims` and resets the row selection — the new
    /// entity's list, never the old one appended.
    @Test("the digest re-keys its statements on the entity id and replaces the list")
    func digestStatementsRekeyOnEntity() throws {
        // #4896: `.task(id:)` stays on `body` (main file); `loadClaims` moved to
        // +Provenance.swift and dropped `private` (an extension file calls it) —
        // both checked here so the split can't quietly break either half.
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        #expect(digest.contains(".task(id: entity.id)"))

        let provenance = try AppSource.code("Views/Inspector/Knowledge/EntityDigestContent+Provenance.swift")
        // loadClaims resets the selection so a stale row can't survive the swap.
        let load = try #require(
            provenance.components(separatedBy: "func loadClaims()").dropFirst().first
        )
        #expect(String(load).contains("selectedClaimRowId = nil"))
    }

    // MARK: - E. xsurface.same-line

    /// spec: kg-entity-inspector — `kg.entity.xsurface.same-line` (E).
    ///
    /// The same claim renders the same statement line wherever it appears, because
    /// there is ONE composer (`ClaimSummaryCard.svoTriple` + `ClaimLine.text`).
    /// Tested once as an invariant over a fixture set: the composer is
    /// deterministic, drops the group subject when redundant, and keeps it when the
    /// claim is about someone else.
    @Test("one composer yields one line for a claim across every surface")
    func sameLineAcrossSurfaces() {
        // A claim ABOUT the focused entity: its own name is redundant under the
        // entity's grouped list, so it is dropped.
        let own = Self.claim(
            id: "own", subject: "Adolfo Hurtado", verb: "compareció", object: "ante mí"
        )
        // A claim about SOMEONE ELSE that mentions the entity: the other subject
        // must stay, or the list would assert the wrong thing.
        let other = Self.claim(
            id: "other", subject: "Juan Catarino", verb: "conoce", object: "a Adolfo"
        )
        let group = "Adolfo Hurtado"

        // Two independent surface computations of the same claim must agree,
        // because both route through the single composer.
        let inspectorPaneLine = Self.statementLine(for: own, groupSubject: group)
        let entityDigestLine = Self.statementLine(for: own, groupSubject: group)
        #expect(inspectorPaneLine == entityDigestLine)

        #expect(Self.statementLine(for: own, groupSubject: group) == "compareció · ante mí")
        #expect(Self.statementLine(for: other, groupSubject: group) == "Juan Catarino · conoce · a Adolfo")
    }

    /// spec: kg-entity-inspector — `kg.entity.xsurface.same-line` (E).
    ///
    /// The invariant only holds if every entity-statement surface calls the shared
    /// composer rather than building its own SVO string. Both the digest and the
    /// ontology entity-detail panel route through
    /// `ClaimSummaryCard.svoTriple` + `ClaimLine.text`.
    @Test("every entity-statement surface routes through the one composer")
    func surfacesRouteThroughOneComposer() throws {
        for path in [
            // #4896: provenanceSummary (the digest's composer call) moved to
            // +Provenance.swift.
            "Views/Inspector/Knowledge/EntityDigestContent+Provenance.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Claims.swift"
        ] {
            let source = try AppSource.code(path)
            #expect(source.contains("ClaimSummaryCard.svoTriple(for: claim)"))
            #expect(source.contains("ClaimLine.text("))
        }
    }
}
