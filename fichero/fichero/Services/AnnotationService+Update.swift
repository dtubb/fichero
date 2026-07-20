import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Patch an annotation's note text (and optionally its color/tags). Updates the
    /// in-memory copy on success. Returns `nil` on failure.
    @discardableResult
    func updateText(id: String, text: String) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let response = try await client.api.patchAnnotationApiAnnotationsAnnotationIdPatch(.init(
                path: .init(annotationId: id),
                body: .json(.init(text: text))
            ))
            guard case .ok(let okResponse) = response,
                  let updated = annotation(from: try okResponse.body.json) else {
                error = "Could not update annotation"
                return nil
            }
            if let idx = annotations.firstIndex(where: { $0.id == id }) {
                annotations[idx] = updated
            }
            error = nil
            return updated
        } catch {
            logger.warning("Failed to update annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not update annotation"
            return nil
        }
    }
}
