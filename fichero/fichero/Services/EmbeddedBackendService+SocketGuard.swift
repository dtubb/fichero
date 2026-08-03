import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "UDSSocketProbe")

extension EmbeddedBackendService {

    /// Fail fast, and by name, when the socket we are about to dial is not
    /// being served (#4400).
    ///
    /// SAFETY — this narrows nothing and admits nothing. It can only turn a
    /// slow failure into an immediate one: `.listening` proceeds to the SAME
    /// authenticated readiness probe as before, so an impostor on the socket is
    /// still rejected there, by the launch nonce and the token, exactly as it
    /// was. A `connect(2)` that succeeds is not evidence of anything except
    /// that waiting would have been pointless in a different way.
    ///
    /// Deliberately scoped to the adopt-an-external-engine path, where the
    /// engine is REQUIRED to be up already because that path never spawns. A
    /// path that waits for an engine it just launched must keep waiting: there,
    /// `.absent` is the normal first answer, not a failure.
    ///
    /// Call it OUTSIDE the caller's do/catch. The diagnosis here names the
    /// socket, and `adoptDebugExternalEngine`'s catch would overwrite it with
    /// the generic "start it with start_backend.sh" — which is the misleading
    /// message this exists to replace.
    func requireServedSocket(transportMode: TransportMode) throws {
        guard case let .uds(path) = transportMode else { return }

        let liveness = UDSSocketProbe.liveness(atPath: path)
        guard let diagnosis = UDSSocketProbe.diagnosis(for: liveness, path: path) else { return }

        logger.error("UDS socket not served: \(String(describing: liveness), privacy: .public)")
        self.status = .failed
        errorMessage = diagnosis
        throw BackendError.backendAppNotFound
    }
}
