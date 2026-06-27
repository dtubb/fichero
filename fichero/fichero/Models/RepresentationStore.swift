import Foundation
import Observation
import OSLog

/// Which representations a document offers, and which one the reader is viewing
/// (#2264, reform master plan §H).
///
/// Derived state, not a fetcher: ``ArtifactStore`` already loads a document's
/// artifacts from the backend (the observable-data-layer rule — one endpoint
/// accessor). This store maps that artifact set onto the ``Representation`` kinds
/// and remembers the current selection per document. Views read `available` to
/// build the picker and `selection` to choose canvas content; they never inspect
/// artifacts directly.
@Observable
final class RepresentationStore {
    /// Representations offered for the current document, in menu order. Always
    /// starts with `.image` (the scanned page) followed by any unlocked by an
    /// artifact, deduplicated and ordered by `Representation.allCases`.
    private(set) var available: [Representation] = [.image]

    /// The representation currently shown. Always a member of `available`.
    var selection: Representation = .image {
        didSet {
            if !available.contains(selection) {
                selection = available.first ?? .image
            }
        }
    }

    private(set) var documentId: String?
    private let log = Logger(subsystem: "app.fichero.fichero", category: "RepresentationStore")

    init() {}

    /// Recompute `available` from a document's artifacts.
    ///
    /// When the document changes, selection resets to `.image`. When only the
    /// artifact set changes (same document — e.g. a conversion just finished),
    /// the existing selection is kept if still available so the view doesn't
    /// jump out from under the reader.
    func update(documentId: String, artifacts: [Artifact]) {
        let documentChanged = documentId != self.documentId
        self.documentId = documentId

        var kinds: Set<Representation> = [.image]
        for artifact in artifacts {
            if let rep = Representation.from(artifactType: artifact.artifactType) {
                kinds.insert(rep)
            }
        }
        available = Representation.allCases.filter { kinds.contains($0) }

        if documentChanged {
            selection = .image
        } else if !available.contains(selection) {
            selection = available.first ?? .image
        }

        let kindList = available.map(\.rawValue).joined(separator: ",")
        log.debug(
            "Representations for \(documentId, privacy: .public): \(kindList, privacy: .public)"
        )
    }
}
