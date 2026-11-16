import Foundation

/// The Sharing listener follows the network (`sharing.listener-follows-the-network`, t52): the engine binds the
/// LAN address it had at start, so after a Wi-Fi or DHCP change it says so in health (`sharing.address_changed`)
/// and the app restarts its own engine once, which binds the address the Mac has now. A link minted after that
/// names it.
@MainActor
enum SharingAddressFollower {
    /// The restart that follows a change; at most one per minute, never for a remote engine.
    static let minimumGap: TimeInterval = 60
    private static var lastRestart: Date?
    private static var restarting = false
    /// One restart per change (t73): set after a restart, cleared when health stops saying "changed". A restart that
    /// did not cure it is not repeated every minute.
    private static var restartedForThisChange = false

    /// Health no longer says the address changed: the next change may restart again.
    static func clear() { restartedForThisChange = false }

    static func shouldRestart(changed: Bool, engineIsLocal: Bool, now: Date, last: Date?, restarting: Bool) -> Bool {
        guard changed, engineIsLocal, !restarting else { return false }
        guard let last else { return true }
        return now.timeIntervalSince(last) >= minimumGap
    }

    /// Lets a health check that sees the change restart the local engine.
    static func install(appState: AppState, backendService: EmbeddedBackendService) {
        appState.onSharingAddressChanged = {
            guard !restartedForThisChange,
                  shouldRestart(changed: true, engineIsLocal: EngineConfig.engineIsLocal, now: Date(),
                                last: lastRestart, restarting: restarting) else { return }
            restartedForThisChange = true
            restarting = true
            lastRestart = Date()
            defer { restarting = false }
            backendService.stop()
            do {
                try await backendService.start()
                if EmbeddedBackendService.needsAnotherStart(status: backendService.status) {
                    try await backendService.start()
                }
            } catch {
                appState.engine.markUnreachable(error.localizedDescription)
            }
            await appState.checkBackendHealth()
        }
    }
}
