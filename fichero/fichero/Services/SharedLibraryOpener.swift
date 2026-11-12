import Foundation
import SwiftUI

/// Opens a library a paired Mac shared with this person (`sharing.guest.row-opens-its-library`, #6360). The library is
/// PINNED to that Mac (`sharing.guest.library-pinned-to-its-host`, #2866): it opens beside the local projects, dials its own
/// host, and this Mac's engine and the app-wide host are left alone. The device token is already in the Keychain.
@MainActor
enum SharedLibraryOpener {
    static func open(hostRoot: String, libraryPath: String, libraryManager: LibraryManager) async {
        guard let apiRoot = URL(string: hostRoot) else { return }
        let previous = libraryManager.currentLibraryId
        let alreadyOpen = libraryManager.openLibraries.contains { $0.url.path == libraryPath && $0.host.url == apiRoot }
        guard let library = libraryManager.switchToRemoteLibrary(path: libraryPath, pinnedTo: apiRoot) else { return }
        do {
            _ = try await library.apiClient.healthCheck()
        } catch {
            // Back to what was on screen (`sharing.alerts.one-alert-per-failure`).
            libraryManager.dropPinnedLibrary(alreadyOpen ? nil : library.id, backTo: previous)
            let name = PairedMachineStore.load().first { $0.id == hostRoot }?.name ?? apiRoot.host ?? "That Mac"
            let words = failureWords(for: error, host: name)
            libraryManager.sharingFailure = SharingFailurePrompt.make(
                title: words.title, sentence: words.sentence,
                retry: !words.canRetry ? nil : {
                    Task { await open(hostRoot: hostRoot, libraryPath: libraryPath, libraryManager: libraryManager) }
                },
                copy: { PlatformPasteboard.writeString($0) })
        }
    }

    /// Lets a Shared Libraries row open its library (#6360).
    static func install(libraryManager: LibraryManager) {
        libraryManager.openSharedLibrary = { machine, path in
            await open(hostRoot: machine.id, libraryPath: path, libraryManager: libraryManager)
        }
    }

    /// The connect sheet shows at an Option launch and when File ▸ Connect to Library… asks.
    static func connectSheet(_ libraryManager: LibraryManager, optionLaunch: Binding<Bool>) -> Binding<Bool> {
        Binding(
            get: { optionLaunch.wrappedValue || libraryManager.connectToLibraryRequested },
            set: { if !$0 { optionLaunch.wrappedValue = false; libraryManager.connectToLibraryRequested = false } })
    }

    /// iPhone and iPad (`sharing.ios.shared-library-chooser`): no local engine to stop, so the host and library are
    /// written and the phone's one connect path (`reconnect`) dials them.
    static func openOnDevice(
        hostRoot: String, libraryPath: String, appState: AppState, libraryManager: LibraryManager,
        reconnect: () async -> Void
    ) async {
        guard let apiRoot = URL(string: hostRoot) else { return }
        EngineConfig.storeHost(hostRoot)
        EngineConfig.defaults.set(libraryPath, forKey: RemoteAccessConfig.pairedLibraryPathKey)
        PairedHostEndpointStore.clear()
        PairedHostEndpointStore.record(apiRoot)
        appState.reconfigureGeneratedClientsForCurrentHost()
        libraryManager.reconfigureGeneratedClientsForCurrentHost()
        libraryManager.adoptPairedRemoteLibrary()
        await reconnect()
        // Already connected to this host: the connect above changes nothing, so the chosen library loads here (#6555).
        if libraryManager.backendIsReady, let library = libraryManager.globalLibrary {
            await libraryManager.loadLibraryDataIfNeeded(for: library)
        }
    }

    /// Lets a sidebar row of a paired Mac's library open it on iPhone and iPad (#6555). Only the Mac installed this, so on the
    /// iPad the row set a "connect" request no sheet answers and tapping it did nothing.
    static func installOnDevice(libraryManager: LibraryManager, appState: AppState, reconnect: @escaping () async -> Void) {
        libraryManager.openSharedLibrary = { machine, path in
            await openOnDevice(
                hostRoot: machine.id, libraryPath: path, appState: appState, libraryManager: libraryManager, reconnect: reconnect)
        }
    }
}
