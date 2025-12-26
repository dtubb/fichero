import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var documentStore = DocumentStore()
    @State private var selectedSidebarItem: SidebarItem?
    @State private var viewMode: AppViewMode = .library(nil)

    // Library items computed from document store
    private var libraryItems: [SidebarItem] {
        documentStore.collections.map { SidebarItem.fromDocument($0) }
    }

    // Search items placeholder
    private var searchItems: [SidebarItem] {
        [] // TODO: Add search items
    }

    // Chat items placeholder
    private var chatItems: [SidebarItem] {
        [] // TODO: Add chat items
    }

    // Workflow items placeholder
    private var workflowItems: [SidebarItem] {
        [] // TODO: Add workflow items
    }

    var body: some View {
        Group {
            if appState.isCheckingBackend {
                // Show loading while checking API
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.5)
                    Text("Connecting to backend...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !appState.isBackendRunning {
                // API not running - show error
                VStack(spacing: 20) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 64))
                        .foregroundColor(.orange)

                    Text("Backend Not Running")
                        .font(.title)
                        .fontWeight(.bold)

                    Text(appState.backendError ?? "Cannot connect to the Fichero API server.")
                        .multilineTextAlignment(.center)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: 400)

                    Divider()
                        .frame(width: 200)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("To start the API, run:")
                            .font(.headline)

                        Text("cd /Users/dtubb/code/fichero_main/fichero")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)

                        Text("PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)
                    }


                    HStack(spacing: 16) {
                        Button("Retry") {
                            Task {
                                await appState.checkBackendHealth()
                            }
                        }
                        .keyboardShortcut("r", modifiers: [.command])

                        Button("Quit") {
                            NSApplication.shared.terminate(nil)
                        }
                        .keyboardShortcut("q", modifiers: [.command])
                    }
                    .padding(.top, 10)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Main content when backend is connected
                NavigationSplitView {
                    SidebarView(
                        viewMode: $viewMode,
                        selectedItem: $selectedSidebarItem,
                        libraryItems: libraryItems,
                        searchItems: searchItems,
                        chatItems: chatItems,
                        workflowItems: workflowItems,
                        onCreateChatWithDocuments: { _ in
                            // Handle document drop for chat
                        }
                    )
                    .environmentObject(documentStore)
                } detail: {
                    // Show detail view based on selected item
                    if let selectedItem = selectedSidebarItem {
                        DetailView(selectedItem: selectedItem)
                    } else {
                        Text("Select an item from the sidebar")
                            .font(.title2)
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
                .task {
                    await documentStore.loadCollections()
                }
            }
        }
    }
}

// Simple detail view for selected sidebar items
struct DetailView: View {
    let selectedItem: SidebarItem?

    var body: some View {
        VStack {
            if let selectedItem = selectedItem {
                Text("Selected: \(selectedItem.name)")
                    .font(.title)
                    .padding()

                Text("Type: \(String(describing: selectedItem.itemType))")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            } else {
                Text("Select an item from the sidebar")
                    .font(.title2)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle(selectedItem?.name ?? "Fichero")
    }
}

#Preview {
    ContentView()
        .environmentObject(AppState())
}