import AppIntents
import FicheroAPIClient
import Foundation

// MARK: - Service accessors for App Intents queries
//
// Mirrors `FicheroIntentSupport.activeActionsService()`: the AppEntity queries
// below resolve and suggest through the active library's EXISTING generated
// services (store/service-only networking, no hand-rolled URLs). One service
// instance per library, shared across windows — see LibraryManager.
extension FicheroIntentSupport {
    @MainActor
    static func activeEntityService() throws -> EntityService {
        let manager = LibraryManager.shared
        if let currentLibraryId = manager.currentLibraryId,
           let currentLibrary = manager.getLibrary(id: currentLibraryId) {
            return currentLibrary.entityService
        }
        if let globalLibrary = manager.globalLibrary {
            return globalLibrary.entityService
        }
        throw FicheroIntentError.noOpenLibrary
    }

    @MainActor
    static func activeDocumentService() throws -> DocumentService {
        let manager = LibraryManager.shared
        if let currentLibraryId = manager.currentLibraryId,
           let currentLibrary = manager.getLibrary(id: currentLibraryId) {
            return currentLibrary.documentService
        }
        if let globalLibrary = manager.globalLibrary {
            return globalLibrary.documentService
        }
        throw FicheroIntentError.noOpenLibrary
    }
}

// MARK: - DocumentAppEntity
//
// Exposes a Fichero document to Shortcuts / Siri / App Intents so other
// intents and shortcuts can reference a specific document by id (#1837).
// Deliberately minimal: id + name + the query. We do NOT mirror every field
// of the `Document` model — Shortcuts only needs a stable identity and a label.
struct DocumentAppEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Document")
    static let defaultQuery = DocumentEntityQuery()

    let id: String
    let name: String

    init(id: String, name: String) {
        self.id = id
        self.name = name
    }

    init(_ document: Document) {
        self.id = document.id
        self.name = document.name
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)")
    }
}

struct DocumentEntityQuery: EntityQuery {
    @MainActor
    func entities(for identifiers: [String]) async throws -> [DocumentAppEntity] {
        let service = try FicheroIntentSupport.activeDocumentService()
        var results: [DocumentAppEntity] = []
        for id in identifiers {
            // Best-effort: skip ids that no longer resolve rather than failing
            // the whole batch (a Shortcut may reference a deleted document).
            if let document = try? await service.getDocument(id) {
                results.append(DocumentAppEntity(document))
            }
        }
        return results
    }

    @MainActor
    func suggestedEntities() async throws -> [DocumentAppEntity] {
        let service = try FicheroIntentSupport.activeDocumentService()
        let roots = try await service.getRoots()
        return roots.map(DocumentAppEntity.init)
    }
}

// MARK: - EntityAppEntity (knowledge entity)
//
// Exposes a knowledge entity (person, place, organization, …) to App Intents.
// Backed by the OpenAPI-generated `KnowledgeEntity`; minimal projection of
// id + canonical name.
struct EntityAppEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Knowledge Entity")
    static let defaultQuery = KnowledgeEntityQuery()

    let id: String
    let canonicalName: String

    init(id: String, canonicalName: String) {
        self.id = id
        self.canonicalName = canonicalName
    }

    /// Fails when the source entity has no id (unsaved / merged-away rows).
    init?(_ entity: Components.Schemas.KnowledgeEntity) {
        guard let id = entity.id else { return nil }
        self.id = id
        self.canonicalName = entity.canonicalName
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(canonicalName)")
    }
}

struct KnowledgeEntityQuery: EntityQuery {
    @MainActor
    func entities(for identifiers: [String]) async throws -> [EntityAppEntity] {
        let service = try FicheroIntentSupport.activeEntityService()
        var results: [EntityAppEntity] = []
        for id in identifiers {
            if let entity = try? await service.getEntity(id),
               let appEntity = EntityAppEntity(entity) {
                results.append(appEntity)
            }
        }
        return results
    }

    @MainActor
    func suggestedEntities() async throws -> [EntityAppEntity] {
        let service = try FicheroIntentSupport.activeEntityService()
        let entities = try await service.listEntities(limit: 25)
        return entities.compactMap(EntityAppEntity.init)
    }
}

// MARK: - ClaimAppEntity (knowledge claim)
//
// Exposes a knowledge claim to App Intents. Backed by the OpenAPI-generated
// `KnowledgeClaim`; minimal projection of id + claim text.
struct ClaimAppEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Knowledge Claim")
    static let defaultQuery = KnowledgeClaimQuery()

    let id: String
    let text: String

    init(id: String, text: String) {
        self.id = id
        self.text = text
    }

    /// Fails when the source claim has no id.
    init?(_ claim: Components.Schemas.KnowledgeClaim) {
        guard let id = claim.id else { return nil }
        self.id = id
        self.text = claim.text
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(text)")
    }
}

struct KnowledgeClaimQuery: EntityQuery {
    @MainActor
    func entities(for identifiers: [String]) async throws -> [ClaimAppEntity] {
        let service = try FicheroIntentSupport.activeEntityService()
        var results: [ClaimAppEntity] = []
        for id in identifiers {
            if let claim = try? await service.getClaim(id),
               let appEntity = ClaimAppEntity(claim) {
                results.append(appEntity)
            }
        }
        return results
    }

    @MainActor
    func suggestedEntities() async throws -> [ClaimAppEntity] {
        let service = try FicheroIntentSupport.activeEntityService()
        let claims = try await service.listClaims(limit: 25)
        return claims.compactMap(ClaimAppEntity.init)
    }
}

// ponytail: Spotlight donation is a deliberate follow-up. Making these
// AppEntity types conform to `IndexedEntity` and donating `CSSearchableItem`s
// (so documents/entities/claims show up in system Spotlight search) is the
// macOS-26 / Golden Gate SDK-heavy half of #1837 and is intentionally deferred.
