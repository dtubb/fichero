import Foundation

/// The ONE way this app changes which engine it talks to (sharing.one-writer-of-the-engine-host, #5916): stop the
/// engine, write the host, point the clients at it, start, reconnect, and put the previous host back if the new one does
/// not answer. Settings › Engine › Advanced › Apply and Settings › Sharing › Connect This Mac both call it, so they
/// cannot drift into two procedures for one setting.
@MainActor
struct EngineHostSwitch {
    var stop: () -> Void
    /// The only place the stored host is written.
    var setHost: (String) -> Void
    /// Point the generated clients (and the library) at the host just written.
    var repoint: () -> Void
    var start: () async throws -> Void
    /// Read the engine's health after a start; true when it answers.
    var reconnect: () async -> Bool
    /// Even the previous host would not start again.
    var onRestoreFailure: (Error) -> Void = { _ in }

    /// Switch from `previous` to `attempted`. An unchanged host is not restarted, but it IS repointed and reconnected: a
    /// re-pair after a revoke picks up new credentials and must read the engine's health again, or the status stays
    /// failed. A new host that does not answer throws `notResponding` after the previous host has been put back.
    func run(from previous: String, to attempted: String, notResponding: String,
             onFailure: (String) -> Void = { _ in }) async throws {
        guard attempted != previous else {
            repoint()
            guard await reconnect() else { throw EngineHostSwitchError.notResponding(notResponding) }
            return
        }
        stop()
        setHost(attempted)
        repoint()
        do {
            try await start()
            guard await reconnect() else { throw EngineHostSwitchError.notResponding(notResponding) }
        } catch {
            onFailure(attempted)
            stop()
            setHost(previous)
            repoint()
            do {
                try await start()
                _ = await reconnect()
            } catch {
                onRestoreFailure(error)
            }
            throw error
        }
    }
}

extension EngineHostSwitch {
    /// The switch both screens use: the embedded engine is stopped and started around the change, the clients and the
    /// library are repointed, and "reconnected" means the engine answered a health read. `setHost` is the caller's
    /// storage for the host (the screens' @AppStorage), written only from here.
    static func standard(
        appState: AppState, backendService: EmbeddedBackendService, libraryManager: LibraryManager,
        setHost: @escaping (String) -> Void
    ) -> EngineHostSwitch {
        EngineHostSwitch(
            stop: { backendService.stop() },
            setHost: setHost,
            repoint: {
                libraryManager.adoptPairedRemoteLibrary()
                appState.reconfigureGeneratedClientsForCurrentHost()
                libraryManager.reconfigureGeneratedClientsForCurrentHost()
            },
            start: { try await backendService.start() },
            reconnect: {
                await appState.checkBackendHealth()
                guard appState.isBackendRunning else {
                    backendService.status = .failed
                    backendService.errorMessage = appState.backendError
                    return false
                }
                backendService.status = .running
                backendService.errorMessage = nil
                appState.startBackendHeartbeat()
                await KnownLibraryRegistryStore.shared.refresh()
                libraryManager.adoptPairedRemoteLibrary()
                await libraryManager.adoptHostLibraryWhenPairingCarriedNone()
                await libraryManager.backendDidBecomeReady()
                return true
            },
            onRestoreFailure: { error in
                backendService.status = .failed
                backendService.errorMessage = error.localizedDescription
            })
    }
}

enum EngineHostSwitchError: LocalizedError {
    case notResponding(String)

    var errorDescription: String? {
        switch self {
        case .notResponding(let message): message
        }
    }
}
