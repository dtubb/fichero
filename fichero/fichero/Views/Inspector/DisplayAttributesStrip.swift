import SwiftUI

/// Compact key-value strip at the top of the V2 inspector — modeled on
/// Tinderbox's "Displayed Attributes" panel. Read-only in Phase 1.
///
/// Shows the few fields a researcher checks most often when scanning a
/// document: status, kind, ingest mode, timestamps. The list is intentionally
/// short — anything more belongs in the Info tab. See
/// docs/contributor/architecture/fichero/inspector_redesign.md.
struct DisplayAttributesStrip: View {
    let document: Document

    // Artifacts are loaded lazily so the user can opt to surface them as rows
    // (#1229 part 2). The same per-document, non-descendant scope the Artifacts
    // tab uses (#721) — a page shows only its own artifacts.
    @Environment(ArtifactStore.self) var artifactStore

    /// Which fixed attributes the user has *hidden*, comma-joined raw values.
    /// Persisted as a global display preference (not per-window scene state) —
    /// the visible set is user-editable, never hardcoded (MEMORY: don't
    /// hardcode user-editable things). Default empty → every fixed attribute
    /// shows, matching pre-#1229 behaviour.
    @AppStorage("inspector.attributeStrip.hidden") var hiddenRaw: String = ""
    /// Artifact types the user has chosen to surface, comma-joined. Default
    /// empty → no artifacts shown; they are opt-in.
    @AppStorage("inspector.attributeStrip.artifacts") var shownArtifactsRaw: String = ""
    /// Knowledge-graph summaries surfaced at the top of the Content pane,
    /// comma-joined. Defaults to "entities" so the inspector reflects what's
    /// actually been extracted on the page — the entities row appears as the
    /// page gains entities (gated on a non-zero count in `rows`) — instead of
    /// staying blank by default (#2696). Claims remain opt-in. Still
    /// user-editable via the filter menu (#1246). Per-kind people/places rows
    /// are the larger design pass.
    @AppStorage("inspector.attributeStrip.kg") var shownKGRaw: String = "entities"
    /// Scope for KG summaries. Defaults to the item's OWN records so a
    /// folder/PDF shows what belongs to it, not its children's mixed in
    /// (#2697); children are opt-in via the "Include children" toggle.
    @AppStorage("inspector.scope.includeChildren") var includeChildren: Bool = false
    /// Document-metadata keys the user has surfaced, comma-joined. File
    /// metadata/info and any imported JSON all live in `document.metadata`,
    /// so this one bucket covers both. Opt-in (#1246).
    @AppStorage("inspector.attributeStrip.metadata") var shownMetadataRaw: String = ""

    /// Knowledge-graph reads come from the same service the KG tab uses.
    @Environment(EntityService.self) var entityService

    /// The shared KG stores the Entities/Claims tabs render from. The strip
    /// doesn't derive its counts from them directly — its counts honour the
    /// includeChildren toggle and ClaimStore is scope-based, neither of which the
    /// per-document store exposes — but it OBSERVES them so a mutation refreshes
    /// the canonical count query, keeping the strip from contradicting the tabs
    /// (#3618).
    @Environment(EntityStore.self) private var entityStore
    @Environment(ClaimStore.self) private var claimStore

    /// Generated artifacts for this document, observed from the shared
    /// ArtifactStore rather than a view-local fetch (#3427).
    var artifacts: [Artifact] { artifactStore.items }
    /// KG counts for this document, nil until loaded (or on load failure).
    /// Drives the opt-in Entities/Claims rows (#1246).
    @State var entityCount: Int?
    @State var claimCount: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ForEach(Array(rows.enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                }
                rowView(for: item)
            }
        }
        .padding(.vertical, 6)
        .background(Color(.controlBackgroundColor))
        .task(id: document.id) {
            // Artifacts and KG counts are independent reads — fetch them
            // concurrently so the strip populates without serial latency.
            async let artifactLoad: Void = loadArtifacts()
            async let knowledgeLoad: Void = loadKnowledgeGraph()
            _ = await (artifactLoad, knowledgeLoad)

            // Normalize persisted CSV payloads so malformed/empty tokens from older
            // builds don't keep toggles in an inconsistent state across launches.
            hiddenRaw = csvString(hiddenAttributes)
            shownArtifactsRaw = csvString(shownArtifactTypes)
            shownKGRaw = csvString(shownKGItems)
            shownMetadataRaw = csvString(shownMetadataKeys)
        }
        // Keep the strip's KG counts consistent with the Entities/Claims tabs
        // (#3618): when the shared stores mutate (change-stream #1863 — merge,
        // add, delete), re-run the canonical count query instead of showing a
        // stale one-shot count that contradicts the tab.
        .onChange(of: entityStore.entitiesByDocumentId[document.id]?.count) {
            Task { await loadKnowledgeGraph() }
        }
        .onChange(of: claimStore.claims.count) {
            Task { await loadKnowledgeGraph() }
        }
    }
}
