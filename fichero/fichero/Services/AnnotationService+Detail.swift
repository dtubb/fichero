import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Fetch the latest server copy for one annotation and merge it into the list.
    @discardableResult
    func getAnnotation(id: String) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let response = try await client.api.getAnnotationApiAnnotationsAnnotationIdGet(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok(let okResponse) = response,
                  let annotation = annotation(from: try okResponse.body.json) else {
                error = "Could not load annotation"
                return nil
            }
            if let index = annotations.firstIndex(where: { $0.id == annotation.id }) {
                annotations[index] = annotation
            } else {
                annotations.insert(annotation, at: 0)
            }
            error = nil
            return annotation
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.warning("Failed to fetch annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load annotation"
            return nil
        }
    }
}
