import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Delete an annotation and remove it from `annotations`. Returns `true` on success.
    @discardableResult
    func delete(id: String) async -> Bool {
        syncLibraryPath()
        do {
            let response = try await client.api.deleteAnnotationApiAnnotationsAnnotationIdDelete(.init(
                path: .init(annotationId: id),
            ))
            guard case .noContent = response else {
                error = "Could not delete annotation"
                return false
            }
            annotations.removeAll { $0.id == id }
            error = nil
            return true
        } catch {
            logger.warning("Failed to delete annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not delete annotation"
            return false
        }
    }
}
