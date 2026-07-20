import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Promote a highlight/note annotation into a KnowledgeClaim.
    @discardableResult
    func promoteToClaim(id: String) async -> Bool {
        syncLibraryPath()
        do {
            let response = try await client.api.promoteToClaimApiAnnotationsAnnotationIdPromoteToClaimPost(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok = response else {
                error = "Could not promote annotation"
                return false
            }
            error = nil
            return true
        } catch {
            logger.warning("Failed to promote annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not promote annotation"
            return false
        }
    }
}
