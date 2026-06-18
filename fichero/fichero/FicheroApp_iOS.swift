#if canImport(UIKit) && !os(macOS)
import OSLog
import SwiftUI

@main
struct FicheroAppIOS: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroAppIOS")

    @StateObject private var backendService = EmbeddedBackendService()
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()
    @StateObject private var libraryManager = LibraryManager.shared
    @StateObject private var windowState = WindowState(libraryId: LibraryManager.globalLibraryId)
    @StateObject private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared
    @State private var executionObserver = WorkflowExecutionObserver()

    var body: some Scene {
        WindowGroup {
            FicheroSharedPlatformRoot(
                windowState: windowState,
                executionObserver: executionObserver
            )
                .environmentObject(backendService)
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .environmentObject(libraryManager)
                .environmentObject(claimFocusState)
                .environmentObject(appState.mcpService)
                .environment(kgFocusState)
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

private struct FicheroSharedPlatformRoot: View {
    @EnvironmentObject private var libraryManager: LibraryManager

    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    private var activeLibrary: LibraryManager.LibraryReference? {
        if let currentLibraryId = libraryManager.currentLibraryId,
           let library = libraryManager.getLibrary(id: currentLibraryId) {
            return library
        }

        if let library = libraryManager.getLibrary(id: windowState.libraryId) {
            return library
        }

        return libraryManager.globalLibrary
    }

    var body: some View {
        Group {
            if let library = activeLibrary {
                LibraryWorkspaceRoot(library: library, executionObserver: executionObserver)
                    .environmentObject(windowState)
                    .environmentObject(library.apiClient)
            } else {
                ContentUnavailableView(
                    "Library Unavailable",
                    systemImage: "externaldrive.badge.exclamationmark",
                    description: Text("Fichero could not load the Local library.")
                )
            }
        }
    }
}
#endif
