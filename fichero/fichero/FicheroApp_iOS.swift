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
                    do {
                        try await backendService.start()
                        await KnownLibraryRegistryStore.shared.refresh()
                        await libraryManager.backendDidBecomeReady()
                    } catch {
                        logger.error("Failed to start backend: \(error.localizedDescription)")
                    }
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
