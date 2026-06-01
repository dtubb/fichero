import AppKit
import SwiftUI

// swiftlint:disable:next type_body_length
struct FirstRunWindow: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var featureManager = FeatureManager.shared
    @ObservedObject private var libraryManager = LibraryManager.shared

    @State private var step: FirstRunStep = .welcome
    @State private var selectedLibraryName: String?
    @State private var documentsPermission = false
    @State private var openRouterKey = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: 760, height: 520)
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Fichero")
                .font(.title2.weight(.semibold))
                .padding(.bottom, 12)

            ForEach(FirstRunStep.allCases) { item in
                Button {
                    step = item
                } label: {
                    Label(item.title, systemImage: item.icon)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 7)
                        .padding(.horizontal, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(step == item ? Color.accentColor.opacity(0.14) : Color.clear)
                        )
                }
                .buttonStyle(.plain)
            }

            Spacer()
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
        .frame(width: 220)
        .background(Color(nsColor: .controlBackgroundColor))
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:
            stepPage(
                title: "Welcome to Fichero",
                subtitle: "A research workspace for scanned sources, PDFs, notes, and knowledge graphs.",
                systemImage: "doc.richtext"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "books.vertical",
                        title: "Start with a library",
                        body: "Choose where your source collection lives, then Fichero can keep scans, PDFs, notes, and graphs together.",
                        primaryTitle: "Set Up Library",
                        primaryIcon: "arrow.right",
                        primaryAction: { step = .library }
                    ),
                    footer: {
                        HStack(spacing: 8) {
                            detailPill("Local-first", icon: "desktopcomputer")
                            detailPill("Knowledge graph ready", icon: "point.3.connected.trianglepath.dotted")
                            // Surface the Research workspace at first run so it's
                            // discoverable — it lives behind the flask icon in the
                            // sidebar mode bar (⌃⌘8). (#1499)
                            detailPill("Research workspace (⌃⌘8)", icon: "flask")
                        }
                    }
                )
            }
        case .library:
            stepPage(
                title: "Library Setup",
                subtitle: "Start with a new package or connect an existing .fichero library.",
                systemImage: "folder"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "folder.badge.gearshape",
                        title: "Choose your working library",
                        body: selectedLibraryName.map { "Selected library: \($0)" }
                            ?? "Create a new library package or open an existing folder before importing documents.",
                        primaryTitle: selectedLibraryName == nil ? "Create Library" : "Continue",
                        primaryIcon: selectedLibraryName == nil ? "plus" : "arrow.right",
                        primaryAction: {
                            if selectedLibraryName == nil {
                                let library = libraryManager.createNewLibrary()
                                selectedLibraryName = library.displayName
                            } else {
                                step = .permissions
                            }
                        }
                    ),
                    footer: {
                        HStack(spacing: 10) {
                            Button {
                                openExistingLibraryPanel()
                            } label: {
                                Label("Open Existing", systemImage: "folder")
                            }
                            if let selectedLibraryName {
                                Label(selectedLibraryName, systemImage: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                    .lineLimit(1)
                            }
                        }
                    }
                )
            }
        case .permissions:
            stepPage(
                title: "Permissions",
                subtitle: "Grant access only to the locations Fichero should work with.",
                systemImage: "lock.shield"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: documentsPermission ? "checkmark.shield" : "lock.shield",
                        title: "Authorize source locations",
                        body: documentsPermission
                            ? "Documents access is ready. Enable Photos or Accessibility later if a workflow needs it."
                            : "Grant folder access only for the locations Fichero should scan and organize.",
                        primaryTitle: documentsPermission ? "Continue" : "Choose Folder",
                        primaryIcon: documentsPermission ? "arrow.right" : "folder.badge.gearshape",
                        primaryAction: {
                            if documentsPermission {
                                step = .cloud
                            } else {
                                requestDocumentsAccess()
                            }
                        }
                    ),
                    footer: {
                        HStack(spacing: 10) {
                            Button {
                                openSettingsPane("x-apple.systempreferences:com.apple.preference.security?Privacy_Photos")
                            } label: {
                                Label("Photos", systemImage: "photo.on.rectangle")
                            }
                            Button {
                                openSettingsPane("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
                            } label: {
                                Label("Accessibility", systemImage: "figure.wave")
                            }
                            if documentsPermission {
                                detailPill("Documents ready", icon: "checkmark.circle.fill")
                            }
                        }
                    }
                )
            }
        case .cloud:
            stepPage(
                title: "Cloud LLM",
                subtitle: "Optional OpenRouter setup for the $medium fallback tier.",
                systemImage: "cloud"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "cloud",
                        title: "Add a capable fallback",
                        body: "OpenRouter is optional. Configure it now to handle structured extraction "
                            + "when local providers are unavailable.",
                        primaryTitle: openRouterKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? "Finish Without Cloud"
                            : "Save and Finish",
                        primaryIcon: "checkmark",
                        primaryAction: { Task { await saveAndFinish() } }
                    ),
                    footer: {
                        SecureField("OpenRouter API key", text: $openRouterKey)
                            .textFieldStyle(.roundedBorder)
                        Text("Leave blank to configure cloud models later in Settings.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                )
            }
        }
    }

    private func stepPage<Content: View>(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder body: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                Image(systemName: systemImage)
                    .font(.system(size: 28))
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 42, height: 42)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.title.weight(.semibold))
                    Text(subtitle)
                        .foregroundStyle(.secondary)
                }
            }

            body()

            Spacer()
            HStack {
                Button("Skip") { finish() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Back") { step = step.previous }
                    .disabled(step == .welcome)
                Button(step == .cloud ? "Finish" : "Continue") {
                    if step == .cloud {
                        Task { await saveAndFinish() }
                    } else {
                        step = step.next
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSaving)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
    }

    private func firstRunCard<Footer: View>(_ config: FirstRunCardConfig, @ViewBuilder footer: () -> Footer) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: config.icon)
                .font(.system(size: 36, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 64, height: 64)
                .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))

            VStack(alignment: .leading, spacing: 8) {
                Text(config.title)
                    .font(.title3.weight(.semibold))
                Text(config.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            footer()

            Spacer()

            Button(action: config.primaryAction) {
                Label(config.primaryTitle, systemImage: config.primaryIcon)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(isSaving)
        }
        .padding(22)
        .frame(maxWidth: .infinity, minHeight: 280, alignment: .leading)
        .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        }
        .shadow(color: Color.black.opacity(0.04), radius: 12, x: 0, y: 4)
    }

    private func detailPill(_ title: String, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
    }

    private func openLibrary(_ url: URL) {
        let library = libraryManager.openLibrary(at: url)
        selectedLibraryName = library.displayName
    }

    private func openExistingLibraryPanel() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Open Library"
        if panel.runModal() == .OK, let url = panel.url {
            openLibrary(url)
        }
    }

    private func requestDocumentsAccess() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK {
            documentsPermission = true
        }
    }

    private func openSettingsPane(_ rawURL: String) {
        guard let url = URL(string: rawURL) else { return }
        NSWorkspace.shared.open(url)
    }

    private func saveAndFinish() async {
        isSaving = true
        defer { isSaving = false }
        let trimmedKey = openRouterKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedKey.isEmpty {
            do {
                _ = try await appState.providerService.createProvider(
                    providerType: "openrouter",
                    name: "OpenRouter",
                    apiKey: trimmedKey
                )
                await appState.loadProviders()
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }
        finish()
    }

    private func finish() {
        featureManager.firstRunCompleted = true
        UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        dismiss()
    }
}

private struct FirstRunCardConfig {
    let icon: String
    let title: String
    let body: String
    let primaryTitle: String
    let primaryIcon: String
    let primaryAction: () -> Void
}

private enum FirstRunStep: Int, CaseIterable, Identifiable {
    case welcome
    case library
    case permissions
    case cloud

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .library: return "Library"
        case .permissions: return "Permissions"
        case .cloud: return "Cloud LLM"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .permissions: return "lock.shield"
        case .cloud: return "cloud"
        }
    }

    var next: FirstRunStep {
        FirstRunStep(rawValue: min(rawValue + 1, Self.cloud.rawValue)) ?? .cloud
    }

    var previous: FirstRunStep {
        FirstRunStep(rawValue: max(rawValue - 1, Self.welcome.rawValue)) ?? .welcome
    }
}
