import Foundation
import Observation

/// Shared selection holder for the annotation List + detail.
///
/// Mirrors `FocusedArtifact`: the list writes the selected annotation id, and
/// the inline detail plus detached window observe the resolved snapshot.
@Observable
@MainActor
final class FocusedAnnotation {
    static let shared = FocusedAnnotation()

    var id: String?
    private(set) var annotation: DocumentAnnotation?
    var documentName: String?

    init() {}

    func select(_ id: String?, in items: [DocumentAnnotation]) {
        self.id = id
        resolve(in: items)
    }

    func resolve(in items: [DocumentAnnotation]) {
        annotation = id.flatMap { selectedId in items.first { $0.id == selectedId } }
    }

    func clear() {
        id = nil
        annotation = nil
    }
}
