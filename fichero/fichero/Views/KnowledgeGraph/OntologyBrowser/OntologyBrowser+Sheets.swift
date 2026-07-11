import FicheroAPIClient
import SwiftUI

// Sheet + confirmation-dialog modifiers for OntologyBrowser (#1703).
// Extracted from OntologyBrowser.body so the main view stays compact;
// behavior is identical — the modifiers read/write the same `@State` on
// the browser via the passed-in value.

/// Hosts the cluster of `.sheet` / `.confirmationDialog` modifiers for
/// the browser.
struct OntologySheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .modifier(OntologyEntitySheetsModifier(browser: browser))
            .confirmationDialog(
                "Delete this entity?",
                isPresented: Binding(
                    get: { browser.entityPendingDeletion != nil },
                    set: { if !$0 { browser.entityPendingDeletion = nil } }
                ),
                presenting: browser.entityPendingDeletion
            ) { entity in
                Button("Delete \(entity.canonicalName)", role: .destructive) {
                    Task { await browser.deleteEntity(entity) }
                }
                Button("Cancel", role: .cancel) { browser.entityPendingDeletion = nil }
            } message: { _ in
                Text("The entity will be removed along with any claims that reference it (#901).")
            }
    }
}

/// The create / edit / merge / split / predictions sheets. Split out of
/// `OntologySheetsModifier` (#1703) and further chained across two
/// modifiers so each body stays within SwiftLint's function-length limit
/// — behavior is unchanged.
private struct OntologyEntitySheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .modifier(OntologyCreateEditSheetsModifier(browser: browser))
            .modifier(OntologyMergeSplitSheetsModifier(browser: browser))
    }
}

/// Predictions review + create + edit sheets.
private struct OntologyCreateEditSheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .sheet(item: Binding(
                get: { browser.pendingPredictions.map(IdentifiedPredictions.init) },
                set: { newValue in browser.pendingPredictions = newValue?.response }
            )) { wrapped in
                HeuristicReviewSheet(response: wrapped.response) {
                    browser.pendingPredictions = nil
                }
            }
            .sheet(isPresented: Binding(
                get: { browser.showCreateSheet },
                set: { browser.showCreateSheet = $0 }
            )) {
                NewEntitySheet { newEntity in
                    browser.selectedEntityId = newEntity.id
                    browser.showCreateSheet = false
                    Task { await browser.loadEntities() }
                }
            }
            .sheet(item: Binding(
                get: { browser.entityPendingEdit.map(IdentifiedEntity.init) },
                set: { browser.entityPendingEdit = $0?.entity }
            )) { wrapped in
                NewEntitySheet(editing: wrapped.entity) { _ in
                    browser.entityPendingEdit = nil
                    Task { await browser.loadEntities() }
                }
            }
    }
}

/// Merge + split sheets.
private struct OntologyMergeSplitSheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .sheet(item: Binding(
                get: { browser.entityPendingMerge.map(IdentifiedEntity.init) },
                set: { browser.entityPendingMerge = $0?.entity }
            )) { wrapped in
                EntityMergeSheet(
                    absorbingEntity: wrapped.entity,
                    allEntities: browser.entities
                ) {
                    browser.entityPendingMerge = nil
                    Task { await browser.loadEntities() }
                }
            }
            .sheet(item: Binding(
                get: { browser.entityPendingSplit.map(IdentifiedEntity.init) },
                set: { browser.entityPendingSplit = $0?.entity }
            )) { wrapped in
                EntitySplitSheet(
                    primaryEntity: wrapped.entity,
                    allEntities: browser.entities
                ) {
                    browser.entityPendingSplit = nil
                    Task { await browser.loadEntities() }
                }
            }
    }
}
