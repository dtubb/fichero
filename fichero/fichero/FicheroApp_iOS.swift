#if canImport(UIKit) && !os(macOS)
import OSLog
import SwiftUI

@main
struct FicheroAppIOS: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroAppIOS")

    @StateObject private var backendService = EmbeddedBackendService()
    @StateObject private var appState = AppState()
    @StateObject private var libraryManager = LibraryManager.shared

    var body: some Scene {
        WindowGroup {
            FicheroIOSPlaceholderRoot()
                .environmentObject(backendService)
                .environmentObject(appState)
                .environmentObject(libraryManager)
                .task {
                    await appState.checkBackendHealth()
                    guard appState.isBackendRunning else {
                        logger.error(
                            "External backend is not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
                        )
                        return
                    }

                    await KnownLibraryRegistryStore.shared.refresh()
                    await libraryManager.backendDidBecomeReady()
                }
        }
    }
}

struct FicheroIOSPlaceholderRoot: View {
    var body: some View {
        Text("Fichero iOS root view — replace me")
    }
}
#endif
