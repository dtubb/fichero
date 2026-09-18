@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// Tests for `EntityRow`'s display-label fallback (#4705 increment 3: moved
/// out of `OntologyBrowserFilterTests.swift` — `EntityRow` is a shared
/// component (`EntityRowView.swift`) with real callers outside the retired
/// KG sidebar mode: `EntityDigestView.swift` (Inspector) and
/// `LibraryView+ListView.swift`. It survives independently of
/// `OntologyBrowser`, which is one of its two current call sites, not its
/// only one.
final class EntityRowTests: XCTestCase {

    func testEntityRowFallbackForEmptyCanonicalName() {
        // An entity with an empty canonicalName must not render as blank — it
        // should fall back to a type+id hint.
        let entity = Components.Schemas.KnowledgeEntity(
            id: "abc123",
            canonicalName: "",
            entityType: .person,
            aliases: [],
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
        // EntityRow.displayLabel: empty name → falls back to "person ·abc123"
        let row = EntityRow(entity: entity, claimCount: 0, style: .browser)
        XCTAssertEqual(row.displayLabelForTesting, "person ·abc123")
    }

    func testEntityRowPassesThroughCleanName() {
        let entity = Components.Schemas.KnowledgeEntity(
            id: "e1",
            canonicalName: "María García",
            entityType: .person,
            aliases: [],
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
        let row = EntityRow(entity: entity, claimCount: 0, style: .browser)
        XCTAssertEqual(row.displayLabelForTesting, "María García")
    }
}
