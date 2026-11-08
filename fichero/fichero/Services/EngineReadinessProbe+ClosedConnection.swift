import Foundation

extension EngineReadinessProbe {
    /// Whether a thrown transport error is the engine having closed (or reset) an idle pooled connection between two probes
    /// (`engine.health.probe-survives-a-closed-keep-alive`, #6372): AsyncHTTPClient's `remoteConnectionClosed`, a reset (ECONNRESET), or
    /// URLSession's `networkConnectionLost`. Read by name so the probe needs no transport import; any other error is not retried.
    nonisolated static func isClosedConnection(_ error: Error) -> Bool {
        if let url = error as? URLError, url.code == .networkConnectionLost { return true }
        let said = "\(error) \((error as NSError).domain) \((error as NSError).code)".lowercased()
        return said.contains("remoteconnectionclosed") || said.contains("connection reset") || said.contains("econnreset")
            || said.contains("connectionreset")
    }
}
