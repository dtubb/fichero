import FicheroAPIClient
import Foundation
import Testing
@testable import Fichero

/// The entities tab detects change via a cheap (id, updatedAt) fingerprint
/// instead of deep-comparing every generated struct (8s main-thread stall on
/// a 2,600-entity Marshall folder, stall.txt 2026-08-19). The fingerprint must
/// be stable for identical content and move for any id/updatedAt/order change.
struct EntityFingerprintTests {
    private func entity(
        id: String, name: String = "x", updatedAt: Date = Date(timeIntervalSince1970: 1000)
    ) -> Components.Schemas.KnowledgeEntity {
        var built = Components.Schemas.KnowledgeEntity(canonicalName: name)
        built.id = id
        built.updatedAt = updatedAt
        return built
    }

    @Test func identicalContentHashesEqual() {
        let first = [entity(id: "1"), entity(id: "2")]
        let second = [entity(id: "1"), entity(id: "2")]
        #expect(DocumentInspectorEntitiesTab.fingerprint(of: first)
            == DocumentInspectorEntitiesTab.fingerprint(of: second))
    }

    @Test func changedUpdatedAtChangesFingerprint() {
        let stale = [entity(id: "1")]
        let touched = [entity(id: "1", updatedAt: Date(timeIntervalSince1970: 2000))]
        #expect(DocumentInspectorEntitiesTab.fingerprint(of: stale)
            != DocumentInspectorEntitiesTab.fingerprint(of: touched))
    }

    @Test func addedRemovedOrReorderedChangesFingerprint() {
        let one = [entity(id: "1")]
        let two = [entity(id: "1"), entity(id: "2")]
        let swapped = [entity(id: "2"), entity(id: "1")]
        #expect(DocumentInspectorEntitiesTab.fingerprint(of: one)
            != DocumentInspectorEntitiesTab.fingerprint(of: two))
        #expect(DocumentInspectorEntitiesTab.fingerprint(of: two)
            != DocumentInspectorEntitiesTab.fingerprint(of: swapped))
    }

    /// Unrelated field churn (aliases, metadata) must NOT change the
    /// fingerprint — that is the whole point: a reload returning the same
    /// (id, updatedAt) set skips regroup + List rediff.
    @Test func unrelatedFieldChurnDoesNotChangeFingerprint() {
        var noisy = entity(id: "1")
        noisy.aliases = ["alias-a", "alias-b"]
        #expect(DocumentInspectorEntitiesTab.fingerprint(of: [entity(id: "1")])
            == DocumentInspectorEntitiesTab.fingerprint(of: [noisy]))
    }
}
