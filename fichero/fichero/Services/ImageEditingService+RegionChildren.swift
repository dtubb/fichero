import Foundation

// Region CHILDREN — derived nodes, not edit-chain operations. In its own
// file because the service file already rides the 400-line limit.
extension ImageEditingService {

    /// Materialize a crop as a NON-DESTRUCTIVE region child node
    /// (`POST /api/images/{id}/crop` → `image.crop_child`): the child carries
    /// `region_in_parent` with "user-crop" confidence and the source is
    /// untouched. Pixel coordinates; the server normalizes against the
    /// source's dimensions. Returns the new child's document id (Daniel,
    /// 2026-08-29: what ▶ runs on when the scope is an ephemeral Preview
    /// marquee).
    func cropChild(
        documentId: String, left: Int, top: Int, width: Int, height: Int, page: Int = 1
    ) async throws -> String {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .cropImageChildApiImagesDocumentIdCropPost(
                path: .init(documentId: documentId),
                body: .json(.init(left: left, top: top, width: width, height: height, page: page)))
            .ok.body.json
        guard let childId = response.child.id else {
            // Prefer raise over silent fallback: a child with no id cannot be
            // run on, and substituting the SOURCE would widen the scope.
            throw ImageEditingError.operationFailed("crop_child returned a child without an id")
        }
        return childId
    }
}
