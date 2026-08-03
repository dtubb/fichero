import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SearchAgreement")

extension SearchResponse {
    /// Check the engine's claim against what arrived, log any disagreement, and
    /// return self unchanged (#4505).
    ///
    /// Returns `self` so the check can sit on the construction expression
    /// without the caller growing a local and a separate `return` — the
    /// `SearchService` class body is at its `type_body_length` limit, and a
    /// diagnostic has no business pushing production code over a threshold.
    ///
    /// It ONLY logs. Reconciling would hide the exact loss it exists to catch,
    /// and adjusting any count would put the engine's tally back into the
    /// header by the back door, undoing #4403.
    @discardableResult
    func reportingSearchAgreement() -> SearchResponse {
        if let diagnosis = SearchAgreement.resolve(for: self).diagnosis {
            logger.error("\(diagnosis, privacy: .public)")
        }
        return self
    }
}
