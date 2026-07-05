import OSLog
import SwiftUI

// Main view for app integrations (DEVONthink, Bookends, Tinderbox)
// swiftlint:disable:next type_body_length
struct IntegrationsView: View {
    @State private var service = IntegrationsService()
    @State private var selectedIntegration: AppIntegration?
    @State private var searchText = ""
    @State private var items: [IntegrationItem] = []
    @State private var isLoadingItems = false
    @State private var itemsError: String?

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "IntegrationsView")

    private var availableIntegrations: [AppIntegration] {
        service.integrations.filter { $0.isAvailable }
    }

    private var unavailableIntegrations: [AppIntegration] {
        service.integrations.filter { !$0.isAvailable }
    }

    var body: some View {
        NavigationSplitView {
            integrationsList
                .navigationSplitViewColumnWidth(min: 200, ideal: 250)
        } detail: {
            if let integration = selectedIntegration {
                integrationDetail(integration)
            } else {
                ContentUnavailableView(
                    "Select an Integration",
                    systemImage: "app.connected.to.app.below.fill",
                    description: Text("Choose an app from the sidebar to browse its contents")
                )
            }
        }
        .task {
            await service.loadIntegrations()
        }
    }

    // MARK: - Integrations List

    private var integrationsList: some View {
        List(selection: $selectedIntegration) {
            Section("Available Apps") {
                ForEach(availableIntegrations) { integration in
                    integrationRow(integration)
                        .tag(integration)
                }
            }

            if !unavailableIntegrations.isEmpty {
                Section("Unavailable") {
                    ForEach(unavailableIntegrations) { integration in
                        integrationRow(integration)
                            .tag(integration)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Integrations")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task {
                        await service.loadIntegrations()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Refresh integrations")
            }
        }
        .overlay {
            if service.isLoading {
                ProgressView()
            }
        }
    }

    private func integrationRow(_ integration: AppIntegration) -> some View {
        HStack {
            Image(systemName: iconForApp(integration.name))
                .foregroundStyle(integration.isAvailable ? .blue : .secondary)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(integration.name)
                    .fontWeight(.medium)

                if let version = integration.version {
                    Text("v\(version)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            Circle()
                .fill(integration.isAvailable ? .green : .red)
                .frame(width: 8, height: 8)
        }
        .contentShape(Rectangle())
    }

    // MARK: - Integration Detail

    // swiftlint:disable:next function_body_length
    private func integrationDetail(_ integration: AppIntegration) -> some View {
        VStack(spacing: 0) {
            // Header
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: iconForApp(integration.name))
                        .font(.largeTitle)
                        .foregroundStyle(.blue)

                    VStack(alignment: .leading) {
                        Text(integration.name)
                            .font(.title2)
                            .fontWeight(.semibold)

                        HStack(spacing: 16) {
                            if let version = integration.version {
                                Label("v\(version)", systemImage: "info.circle")
                            }
                            Label(
                                integration.isAvailable ? "Available" : "Unavailable",
                                systemImage: integration.isAvailable ? "checkmark.circle.fill" : "xmark.circle.fill"
                            )
                            .foregroundStyle(integration.isAvailable ? .green : .red)
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Button {
                        Task {
                            await service.refreshIntegration(integration.name)
                        }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }
            }
            .padding()
            .background(.bar)

            Divider()

            // Search and content
            if integration.isAvailable {
                // Search bar
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("Search \(integration.name)...", text: $searchText)
                        .textFieldStyle(.plain)
                        .onSubmit {
                            Task {
                                await loadItems(from: integration)
                            }
                        }
                    if !searchText.isEmpty {
                        Button {
                            searchText = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(8)
                .background(.background)

                Divider()

                // Items list
                itemsList(for: integration)
            } else {
                ContentUnavailableView(
                    "\(integration.name) Not Available",
                    systemImage: "exclamationmark.triangle",
                    description: Text(integration.error ?? "The app is not installed or not running")
                )
            }
        }
        .onChange(of: selectedIntegration) { _, newValue in
            if newValue != nil {
                searchText = ""
                items = []
                Task {
                    await loadItems(from: newValue!)
                }
            }
        }
    }

    private func itemsList(for integration: AppIntegration) -> some View {
        Group {
            if isLoadingItems {
                ProgressView("Loading items...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = itemsError {
                ContentUnavailableView(
                    "Error Loading Items",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if items.isEmpty {
                ContentUnavailableView(
                    "No Items Found",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text(
                        searchText.isEmpty
                            ? "No items in \(integration.name)"
                            : "No results for \"\(searchText)\""
                    )
                )
            } else {
                List(items) { item in
                    itemRow(item, integration: integration)
                }
                .listStyle(.inset)
            }
        }
    }

    private func itemRow(_ item: IntegrationItem, integration: AppIntegration) -> some View {
        HStack {
            Image(systemName: iconForItemType(item.itemType))
                .foregroundStyle(.secondary)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.name)
                    .lineLimit(2)

                HStack(spacing: 8) {
                    Text(item.itemType)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.quaternary)
                        .cornerRadius(4)

                    if let modified = item.modifiedAt {
                        Text(formatDate(modified))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            Button {
                Task {
                    _ = try? await service.openItem(in: integration.name, externalId: item.externalId)
                }
            } label: {
                Image(systemName: "arrow.up.forward.square")
            }
            .buttonStyle(.borderless)
            .help("Open in \(integration.name)")
        }
        .padding(.vertical, 4)
    }

    // MARK: - Data Loading

    private func loadItems(from integration: AppIntegration) async {
        isLoadingItems = true
        itemsError = nil

        do {
            items = try await service.listItems(
                from: integration.name,
                limit: 100,
                search: searchText.isEmpty ? nil : searchText
            )
        } catch {
            itemsError = error.localizedDescription
            logger.error("Failed to load items: \(error.localizedDescription)")
        }

        isLoadingItems = false
    }

    // MARK: - Helpers

    private func iconForApp(_ name: String) -> String {
        switch name.lowercased() {
        case "devonthink":
            return "folder.badge.gearshape"
        case "bookends":
            return "books.vertical"
        case "tinderbox":
            return "note.text"
        default:
            return "app"
        }
    }

    private func iconForItemType(_ type: String) -> String {
        let lowered = type.lowercased()
        if lowered.contains("pdf") {
            return "doc.fill"
        } else if lowered.contains("reference") || lowered.contains("article") {
            return "doc.text"
        } else if lowered.contains("note") {
            return "note.text"
        } else if lowered.contains("book") {
            return "book"
        } else if lowered.contains("markdown") {
            return "doc.plaintext"
        } else {
            return "doc"
        }
    }

    private func formatDate(_ dateString: String) -> String {
        // Simple date formatting
        if dateString.contains("T") {
            let components = dateString.split(separator: "T")
            return String(components.first ?? "")
        }
        return dateString
    }
}

#Preview {
    IntegrationsView()
}
