import AppIntents
import FicheroAPIClient
import Foundation

enum FicheroIntentError: LocalizedError {
    case noOpenLibrary
    case noSelectedDocuments

    var errorDescription: String? {
        switch self {
        case .noOpenLibrary:
            return "Open a library before running an action."
        case .noSelectedDocuments:
            return "Select at least one document first."
        }
    }
}

enum FicheroIntentSupport {
    @MainActor
    static func activeActionsService() throws -> ActionsService {
        let manager = LibraryManager.shared
        if let currentLibraryId = manager.currentLibraryId,
           let currentLibrary = manager.getLibrary(id: currentLibraryId) {
            return currentLibrary.actionsService
        }
        if let globalLibrary = manager.globalLibrary {
            return globalLibrary.actionsService
        }
        throw FicheroIntentError.noOpenLibrary
    }
}

enum FicheroNoteKindChoice: String, AppEnum {
    case zettel
    case reference
    case hub
    case inbox
    case fleeting
    case permanent

    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Note Kind")

    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [
        FicheroNoteKindChoice.zettel: "Zettel",
        FicheroNoteKindChoice.reference: "Reference",
        FicheroNoteKindChoice.hub: "Hub",
        FicheroNoteKindChoice.inbox: "Inbox",
        FicheroNoteKindChoice.fleeting: "Fleeting",
        FicheroNoteKindChoice.permanent: "Permanent"
    ]
}

enum FicheroAnnotationKindChoice: String, AppEnum {
    case highlight
    case note
    case rating
    case bookmark
    case comment

    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Annotation Kind")

    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [
        FicheroAnnotationKindChoice.highlight: "Highlight",
        FicheroAnnotationKindChoice.note: "Note",
        FicheroAnnotationKindChoice.rating: "Rating",
        FicheroAnnotationKindChoice.bookmark: "Bookmark",
        FicheroAnnotationKindChoice.comment: "Comment"
    ]
}

private struct WorkflowRunItemPayload: Encodable {
    let documentId: String

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
    }
}

private struct WorkflowRunActionPayload: Encodable {
    let workflowId: String
    let items: [WorkflowRunItemPayload]
    // Optional so an unspecified value is omitted (encodeIfPresent) and the
    // backend applies its own default — the FE shouldn't re-decide it (#3304).
    let maxConcurrent: Int?

    enum CodingKeys: String, CodingKey {
        case workflowId = "workflow_id"
        case items
        case maxConcurrent = "max_concurrent"
    }
}

private struct DocumentDeleteActionPayload: Encodable {
    let docId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
    }
}

private func invokeAuditedAction<Params: Encodable & Sendable>(
    _ name: String,
    params: Params
) async throws -> ActionInvokeResult {
    let service = try await FicheroIntentSupport.activeActionsService()
    return try await service.invokeAction(name: name, params: params)
}

struct MergeEntitiesIntent: AppIntent {
    static let title: LocalizedStringResource = "Merge Entities"
    static let description = IntentDescription(
        "Merge one or more entities into a survivor through the audited action registry."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Absorbing Entity ID")
    var absorbingEntityId: String

    @Parameter(title: "Absorbed Entity IDs")
    var absorbedEntityIds: [String]

    @Parameter(title: "Merged Aliases")
    var mergedAliases: [String]?

    @Parameter(title: "Merged Description")
    var mergedDescription: String?

    static var parameterSummary: some ParameterSummary {
        Summary("Merge entities into \(\.$absorbingEntityId)")
    }

    func perform() async throws -> some IntentResult {
        let params = Components.Schemas.EntityMergeRequest(
            absorbingEntityId: absorbingEntityId,
            absorbedEntityIds: absorbedEntityIds,
            mergedAliases: mergedAliases ?? [],
            mergedDescription: mergedDescription?.isEmpty == false ? mergedDescription : nil
        )
        _ = try await invokeAuditedAction("entity.merge", params: params)
        return .result(dialog: "Merged \(absorbedEntityIds.count) entities.")
    }
}

struct CreateNoteIntent: AppIntent {
    static let title: LocalizedStringResource = "Create Note"
    static let description = IntentDescription(
        "Create a free note through the audited action registry."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Body")
    var body: String

    @Parameter(title: "Kind")
    var kind: FicheroNoteKindChoice?

    static var parameterSummary: some ParameterSummary {
        Summary("Create a note")
    }

    func perform() async throws -> some IntentResult {
        let payload = Components.Schemas.FicheroApiRoutesNotesNoteCreateRequest(
            title: nil,
            body: body,
            kind: Components.Schemas.NoteKind(rawValue: (kind ?? FicheroNoteKindChoice.zettel).rawValue)
                ?? Components.Schemas.NoteKind.zettel,
            tags: [],
            linkedNoteIds: [],
            linkedEntityIds: [],
            linkedClaimIds: [],
            linkedDocumentIds: nil,
            pageId: nil,
            folderId: nil,
            linkedStructureNodeId: nil,
            address: nil,
            parentAddress: nil
        )
        _ = try await invokeAuditedAction("note.create", params: payload)
        return .result(dialog: "Created note.")
    }
}

struct DeleteDocumentIntent: AppIntent {
    static let title: LocalizedStringResource = "Delete Document"
    static let description = IntentDescription(
        "Delete a document through the audited action registry."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Document")
    var document: DocumentAppEntity

    static var parameterSummary: some ParameterSummary {
        Summary("Delete document \(\.$document)")
    }

    func perform() async throws -> some IntentResult {
        let payload = DocumentDeleteActionPayload(docId: document.id)
        _ = try await invokeAuditedAction("document.delete", params: payload)
        return .result(dialog: "Deleted document.")
    }
}

struct RunWorkflowIntent: AppIntent {
    static let title: LocalizedStringResource = "Run Workflow"
    static let description = IntentDescription(
        "Run a workflow over selected documents through the audited action registry."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Workflow ID")
    var workflowId: String

    @Parameter(title: "Selected Document IDs")
    var selectedDocumentIds: [String]

    @Parameter(title: "Max Concurrent")
    var maxConcurrent: Int?

    static var parameterSummary: some ParameterSummary {
        Summary("Run workflow \(\.$workflowId)")
    }

    func perform() async throws -> some IntentResult {
        guard !selectedDocumentIds.isEmpty else {
            throw FicheroIntentError.noSelectedDocuments
        }
        let payload = WorkflowRunActionPayload(
            workflowId: workflowId,
            items: selectedDocumentIds.map { WorkflowRunItemPayload(documentId: $0) },
            maxConcurrent: maxConcurrent
        )
        _ = try await invokeAuditedAction("workflow.run", params: payload)
        return .result(dialog: "Started workflow on \(selectedDocumentIds.count) documents.")
    }
}

struct CreateAnnotationIntent: AppIntent {
    static let title: LocalizedStringResource = "Create Annotation"
    static let description = IntentDescription(
        "Create a document annotation through the audited action registry."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Document ID")
    var documentId: String

    @Parameter(title: "Text")
    var text: String?

    @Parameter(title: "Kind")
    var kind: FicheroAnnotationKindChoice?

    @Parameter(title: "Page Label")
    var pageLabel: String?

    static var parameterSummary: some ParameterSummary {
        Summary("Create annotation on \(\.$documentId)")
    }

    func perform() async throws -> some IntentResult {
        let payload = Components.Schemas.AnnotationCreateRequest(
            documentId: documentId,
            pageId: nil,
            folderId: nil,
            kind: Components.Schemas.AnnotationKind(rawValue: (kind ?? FicheroAnnotationKindChoice.note).rawValue)
                ?? Components.Schemas.AnnotationKind.note,
            pageIndex: nil,
            pageLabel: pageLabel,
            charStart: nil,
            charEnd: nil,
            bbox: nil,
            text: text?.isEmpty == false ? text : nil,
            rating: nil,
            color: nil,
            tags: [],
            linkedClaimIds: [],
            linkedEntityIds: [],
            linkedNoteIds: []
        )
        _ = try await invokeAuditedAction("annotation.create", params: payload)
        return .result(dialog: "Created annotation.")
    }
}
