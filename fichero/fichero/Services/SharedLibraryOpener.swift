import Foundation
import SwiftUI

/// Opens a library a paired Mac shared with this person (`sharing.guest.row-opens-its-library`, #6360).
/// Stopgap until each library dials its own host (Step 8.6): the whole app switches to that host through the one
/// `EngineHostSwitch`, the same procedure Pairing and Settings use. The device token is already in the Keychain.
@MainActor
enum SharedLibraryOpener {
    static func open(
        hostRoot: String, libraryPath: String,
        appState: AppState, backendService: EmbeddedBackendService, libraryManager: LibraryManager
    ) async {
        guard let apiRoot = URL(string: hostRoot) else { return }
        let previous = EngineConfig.hostString
        EngineConfig.defaults.set(libraryPath, forKey: RemoteAccessConfig.pairedLibraryPathKey)
        PairedHostEndpointStore.clear()
        PairedHostEndpointStore.record(apiRoot)
        let hostSwitch = EngineHostSwitch.standard(
            appState: appState, backendService: backendService, libraryManager: libraryManager,
            setHost: { EngineConfig.storeHost($0) })
        do {
            try await hostSwitch.run(
                from: previous, to: hostRoot,
                notResponding: "That Mac is not responding. Check that it is on and Sharing is on.")
        } catch {
            libraryManager.sharingStoppedNotice = error.localizedDescription
        }
    }

    /// Lets a Shared Libraries row open its library (#6360).
    static func install(appState: AppState, backendService: EmbeddedBackendService, libraryManager: LibraryManager) {
        libraryManager.openSharedLibrary = { machine, path in
            await open(hostRoot: machine.id, libraryPath: path, appState: appState,
                       backendService: backendService, libraryManager: libraryManager)
        }
    }

    /// The connect sheet shows at an Option launch and when File ▸ Connect to Library… asks.
    static func connectSheet(_ libraryManager: LibraryManager, optionLaunch: Binding<Bool>) -> Binding<Bool> {
        Binding(
            get: { optionLaunch.wrappedValue || libraryManager.connectToLibraryRequested },
            set: { if !$0 { optionLaunch.wrappedValue = false; libraryManager.connectToLibraryRequested = false } })
    }
}
