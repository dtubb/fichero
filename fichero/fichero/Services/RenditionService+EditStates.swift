import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RenditionEditStates")

/// The original and the edited image are two ways the SAME page looks, which
/// is the definition of a rendition — so they belong on the up/down flip the
/// reader already has (Daniel, 2026-09-03: "these should be a rendition so we
/// can easily go back and forth"). Nothing about the node changes, no box
/// moves, and the reader needs no new gesture.
///
/// They are not rows in the `renditions` table: an edit chain is a RECIPE, and
/// the engine renders it on demand at `/api/images/{id}/preview?apply_edits=`.
/// These entries carry an id that says which state they are, and
/// `RenditionService.contentData` renders through that endpoint instead of the
/// rendition-bytes route. Registering a materialised `edited` row server-side
/// is the follow-up (see agent-work/specs/edit-states-as-renditions.md); this
/// is the same sequence, sourced from the recipe.
extension DocumentRendition {
    static let editedRole = "edited"
    static let originalRole = "original"
    /// Marks an id as an edit STATE rather than a stored rendition row.
    static let editStatePrefix = "edit:"

    /// `edit:<role>:<documentId>` — document-scoped on purpose: the content
    /// cache is keyed by rendition id alone, so a constant sentinel would
    /// serve one document's edited pixels for another's.
    static func editStateId(role: String, documentId: String) -> String {
        "\(editStatePrefix)\(role):\(documentId)"
    }

    /// The role encoded in an edit-state id; nil for a real rendition row.
    static func editStateRole(of id: String) -> String? {
        guard id.hasPrefix(editStatePrefix) else { return nil }
        let rest = id.dropFirst(editStatePrefix.count)
        guard let role = rest.split(separator: ":", maxSplits: 1).first, !role.isEmpty else {
            return nil
        }
        return String(role)
    }

    var isEditState: Bool { Self.editStateRole(of: id) != nil }

    /// The two states, given a document's saved operations. Empty when the
    /// document has no edits — there is only one way it looks, and a
    /// one-entry flip strip is noise.
    ///
    /// `existingCount` is how many REAL renditions the engine returned: those
    /// already start at the untouched pixels, so the synthetic "Original" is
    /// added only when it would otherwise be unreachable.
    static func editStates(
        documentId: String,
        operationKinds: [String],
        existingCount: Int
    ) -> [DocumentRendition] {
        guard !operationKinds.isEmpty else { return [] }
        var states: [DocumentRendition] = []
        if existingCount == 0 {
            states.append(
                DocumentRendition(
                    id: editStateId(role: originalRole, documentId: documentId),
                    documentId: documentId,
                    role: originalRole,
                    path: "",
                    isPrimary: false,
                    pixelWidth: nil,
                    pixelHeight: nil,
                    isMaterialized: true,
                    hasOwnFrame: false,
                    note: "The file as imported, before any edits"
                )
            )
        }
        states.append(
            DocumentRendition(
                id: editStateId(role: editedRole, documentId: documentId),
                documentId: documentId,
                role: editedRole,
                path: "",
                isPrimary: false,
                pixelWidth: nil,
                pixelHeight: nil,
                isMaterialized: true,
                // Only a step that moves pixels around gives the render a
                // frame of its own; an enhance leaves every box valid. Stated
                // per chain rather than assumed, so OCR overlays stay drawn
                // when they are still true and skip when they are not.
                hasOwnFrame: operationKinds.contains { frameChangingOps.contains($0) },
                note: "\(operationKinds.count) edit step(s) applied"
            )
        )
        return states
    }

    /// Ops that re-frame the image, so a box normalised to the node's frame no
    /// longer lands where it did.
    static let frameChangingOps: Set<String> = ["crop", "rotate", "straighten"]
}

extension RenditionService {
    /// `items` plus this document's edit states, if it has a saved chain.
    func appendingEditStates(
        to items: [DocumentRendition],
        documentId: String
    ) async -> [DocumentRendition] {
        let kinds = await savedOperationKinds(documentId: documentId)
        let states = DocumentRendition.editStates(
            documentId: documentId,
            operationKinds: kinds,
            existingCount: items.count
        )
        guard !states.isEmpty else { return items }
        // Original first, then whatever the engine staged, then Edited last:
        // the flip runs from least to most processed, and `preferredRendition`
        // lands the reader on Edited.
        let original = states.filter { $0.role == DocumentRendition.originalRole }
        let edited = states.filter { $0.role == DocumentRendition.editedRole }
        return original + items + edited
    }

    /// The `op` names in the document's saved edit chain, in order.
    private func savedOperationKinds(documentId: String) async -> [String] {
        do {
            let response = try await client.api
                .getEditChainApiImagesDocumentIdEditsGet(path: .init(documentId: documentId))
                .ok.body.json
            // The same decode the editor uses — one bridge from the free-form
            // op payload to typed ops, not a second hand-rolled one.
            return try ImageEditingService.chain(from: response).operations.map(\.opKind)
        } catch {
            // A document with no chain is the common case and the endpoint
            // answers it with an empty chain, so anything thrown here is a
            // real fault worth naming — not a state to guess at.
            logger.error(
                "Edit chain unavailable for \(documentId); flipping original↔edited is off: "
                + String(describing: error)
            )
            return []
        }
    }

    /// One edit state's pixels, rendered from the chain by the engine.
    func editStateContent(documentId: String, role: String) async throws -> Data {
        let response = try await client.api.previewImageApiImagesDocumentIdPreviewGet(.init(
            path: .init(documentId: documentId),
            query: .init(applyEdits: role == DocumentRendition.editedRole, page: 1)
        ))
        switch response {
        case .ok(let okResponse):
            let body: OpenAPIRuntime.HTTPBody
            switch okResponse.body {
            case .png(let png): body = png
            case .jpeg(let jpeg): body = jpeg
            }
            return try await Data(collecting: body, upTo: 128 * 1024 * 1024)
        default:
            throw RenditionServiceError.contentUnavailable(
                renditionId: DocumentRendition.editStateId(role: role, documentId: documentId)
            )
        }
    }
}
