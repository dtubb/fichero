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
                VStack(spacing: 12) {
                    onboardingCard(
                        icon: "books.vertical",
                        title: "Library-first",
                        body: "Choose where your source collection lives before importing documents."
                    )
                    onboardingCard(
                        icon: "sparkles",
                        title: "Local by default",
                        body: "Apple Intelligence and local models stay first; cloud models are optional."
                    )
                }
            }
        case .library:
            stepPage(
                title: "Library Setup",
                subtitle: "Start with a new package or connect an existing .fichero library.",
                systemImage: "folder"
            ) {
                VStack(spacing: 12) {
                    HStack(spacing: 12) {
                        actionCard("Create Library", icon: "plus") {
                            let library = libraryManager.createNewLibrary()
                            selectedLibraryName = library.displayName
                        }
                        actionCard("Open Existing", icon: "folder") {
                            openExistingLibraryPanel()
                        }
                    }
                    if let selectedLibraryName {
                        Label(selectedLibraryName, systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                }
            }
        case .permissions:
            stepPage(
                title: "Permissions",
                subtitle: "Grant access only to the locations Fichero should work with.",
                systemImage: "lock.shield"
            ) {
                VStack(spacing: 12) {
                    permissionRow(
                        title: "Documents",
                        detail: documentsPermission ? "Folder access granted" : "Choose a working folder",
                        icon: documentsPermission ? "checkmark.circle.fill" : "folder.badge.gearshape"
                    ) {
                        requestDocumentsAccess()
                    }
                    permissionRow(
                        title: "Photos",
                        detail: "Enable in System Settings if you import from Photos",
                        icon: "photo.on.rectangle"
                    ) {
                        openSettingsPane("x-apple.systempreferences:com.apple.preference.security?Privacy_Photos")
                    }
                    permissionRow(
                        title: "Accessibility",
                        detail: "Only needed for UI automation and XCUITest runs",
                        icon: "figure.wave"
                    ) {
                        openSettingsPane("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
                    }
                }
            }
        case .cloud:
            stepPage(
                title: "Cloud LLM",
                subtitle: "Optional OpenRouter setup for the $medium fallback tier.",
                systemImage: "cloud"
            ) {
                VStack(alignment: .leading, spacing: 12) {
                    SecureField("OpenRouter API key", text: $openRouterKey)
                        .textFieldStyle(.roundedBorder)
                    Text("Leave blank to configure cloud models later in Settings.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
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

    private func onboardingCard(icon: String, title: String, body: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .frame(width: 28)
                .foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline)
                Text(body).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
    }

    private func actionCard(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 10) {
                Image(systemName: icon).font(.largeTitle)
                Text(title).font(.headline)
            }
            .frame(maxWidth: .infinity, minHeight: 118)
        }
        .buttonStyle(.bordered)
    }

    private func permissionRow(
        title: String,
        detail: String,
        icon: String,
        action: @escaping () -> Void
    ) -> some View {
        HStack {
            Label {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.headline)
                    Text(detail).font(.caption).foregroundStyle(.secondary)
                }
            } icon: {
                Image(systemName: icon).foregroundStyle(Color.accentColor)
            }
            Spacer()
            Button("Open", action: action)
        }
        .padding(12)
        .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
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
