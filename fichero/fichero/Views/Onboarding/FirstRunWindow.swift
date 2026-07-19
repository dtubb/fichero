#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

// swiftlint:disable file_length
struct FirstRunWindow: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var featureManager = FeatureManager.shared
    @State private var libraryManager = LibraryManager.shared

    @State private var step: FirstRunStep = .welcome
    @State private var selectedLibraryName: String?
    @State private var documentsPermission = false

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: 760, height: 520)
        .onAppear { surfaceDefaultLibrary() }
    }

    /// #2715 — A new user already lands in a working state: the app-managed
    /// "Local" library (~/Library/Application Support/Fichero/global.fichero) is
    /// always loaded by `LibraryManager` and auto-assigned to the window. Surface
    /// it here so library setup reads as optional, not a blocking step.
    private func surfaceDefaultLibrary() {
        if selectedLibraryName == nil {
            selectedLibraryName = libraryManager.globalLibrary?.displayName
        }
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
        }
        .padding(20)
        .frame(width: 220)
        .background(Color(platformColor: .controlBackgroundColor))
    }
}

// MARK: - Content & builders
extension FirstRunWindow {
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
                        title: "You're ready to go",
                        body: "Fichero already set up a local library so you can start right away. "
                            + "Customize it later — or just begin importing scans, PDFs, notes, and graphs.",
                        primaryTitle: "Get Started",
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
                title: "Library (optional)",
                subtitle: "You already have a working library. Add another only if you want to.",
                systemImage: "folder"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "folder.badge.gearshape",
                        title: "Your working library",
                        body: selectedLibraryName.map {
                            "Ready to use: \($0). You can create more libraries anytime, "
                                + "or save this one to a folder of your choice from the File menu."
                        }
                            ?? "A local library is ready to use. Create more libraries anytime from the File menu.",
                        primaryTitle: "Continue",
                        primaryIcon: "arrow.right",
                        primaryAction: { step = .permissions }
                    ),
                    footer: {
                        // #2716 — "Open Existing" lives in File ▸ Open Library (⌘O)
                        // and Settings, not in first-run onboarding. Keep this step
                        // focused on the ready-to-use default library.
                        if let selectedLibraryName {
                            Label(selectedLibraryName, systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .lineLimit(1)
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
                            ? "Folder access is ready. That's the only permission Fichero needs to get started."
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
                        // #2717 — Folder access is the only permission Fichero needs.
                        // The app declares no Accessibility entitlement (removed) and
                        // no Photos usage string; Photos is requested at import time
                        // only, never up front.
                        if documentsPermission {
                            detailPill("Documents ready", icon: "checkmark.circle.fill")
                        }
                    }
                )
            }
        case .cloud:
            stepPage(
                title: "AI is optional",
                subtitle: "Fichero is local-first. Add a provider only when you want AI.",
                systemImage: "brain"
            ) {
                firstRunCard(
                    FirstRunCardConfig(
                        icon: "cpu",
                        title: "Choose an AI provider",
                        body: "Run models on-device for free with Apple Intelligence, Ollama, or "
                            + "LM Studio, or connect a cloud provider — OpenRouter is an easy default, "
                            + "and OpenAI, Anthropic, or Google work too. Pick your default models; "
                            + "everything is optional and changeable in Settings.",
                        primaryTitle: "Choose a Provider",
                        primaryIcon: "plus",
                        primaryAction: { chooseProviderAndFinish() }
                    ),
                    footer: {
                        // #2718 — local-first, provider-agnostic. Defer to the existing
                        // Add Provider flow (full catalog + default-model selection),
                        // which pre-selects a local provider on first launch. No single
                        // provider is centered.
                        VStack(alignment: .leading, spacing: 10) {
                            // #3121 — surface the zero-cloud on-device options with
                            // their TRUE availability so a fresh user can pick a
                            // private setup knowingly.
                            localFirstAIOptions
                            Text("Prefer to decide later? Skip — you can add providers anytime in Settings.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                )
            }
        }
    }

    /// #3121 — the two zero-cloud, on-device options with their true state.
    /// Apple Intelligence availability comes from the `/providers/apple/availability`
    /// probe (#3118) so an unavailable machine sees the concrete reason instead of
    /// discovering it at first call. MLX is always offered (Apple-silicon local
    /// runtime) with a pointer to its setup pane.
    private var localFirstAIOptions: some View {
        VStack(alignment: .leading, spacing: 8) {
            appleIntelligenceOption
            localOptionRow(
                icon: "cpu",
                title: "MLX on-device models",
                detail: "Set up in Settings ▸ Local LLM.",
                detailTint: .secondary
            )
        }
        .task {
            await appState.appleAvailabilityStore.load()
        }
    }

    @ViewBuilder
    private var appleIntelligenceOption: some View {
        let status = appState.appleAvailabilityStore.status
        localOptionRow(
            icon: "apple.logo",
            title: "Apple Intelligence",
            detail: status.map { $0.available ? "Available" : $0.label } ?? "Checking availability…",
            detailTint: status?.available == false ? .orange : .secondary
        )
    }

    private func localOptionRow(icon: String, title: String, detail: String, detailTint: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .frame(width: 18)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.callout)
            LocalPrivateBadge()
            Spacer()
            Text(detail)
                .font(.caption)
                .foregroundStyle(detailTint)
                .textSelection(.enabled)
                .multilineTextAlignment(.trailing)
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
                    .font(.title2)
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
                        finish()
                    } else {
                        step = step.next
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
    }

    private func firstRunCard<Footer: View>(_ config: FirstRunCardConfig, @ViewBuilder footer: () -> Footer) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: config.icon)
                .font(.largeTitle.weight(.semibold))
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
        }
        .padding(22)
        .frame(maxWidth: .infinity, minHeight: 280, alignment: .leading)
        .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
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

    private func requestDocumentsAccess() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK {
            documentsPermission = true
        }
        #else
        // iOS: document picker / sandbox access would go here.
        documentsPermission = true
        #endif
    }

    /// #2718 — Finish onboarding, then hand off to the existing local-first Add
    /// Provider flow (full provider catalog + default-model selection) rather than
    /// hardcoding any single provider. Setting `isFirstLaunchProviderSetup` makes
    /// that sheet pre-select a local provider.
    private func chooseProviderAndFinish() {
        appState.isFirstLaunchProviderSetup = true
        appState.showAddProvider = true
        finish()
    }

    private func finish() {
        featureManager.firstRunCompleted = true
        UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        dismiss()
    }
}

struct LibrarySetupActionsRow: View {
    let primaryTitle: String
    let primaryIcon: String
    let primaryAction: () -> Void
    let selectedLabel: String?

    var body: some View {
        HStack(spacing: 10) {
            Button(action: primaryAction) {
                Label(primaryTitle, systemImage: primaryIcon)
            }

            if let selectedLabel {
                Label(selectedLabel, systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .lineLimit(1)
            }
        }
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
        case .cloud: return "AI"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .permissions: return "lock.shield"
        case .cloud: return "brain"
        }
    }

    var next: FirstRunStep {
        FirstRunStep(rawValue: min(rawValue + 1, Self.cloud.rawValue)) ?? .cloud
    }

    var previous: FirstRunStep {
        FirstRunStep(rawValue: max(rawValue - 1, Self.welcome.rawValue)) ?? .welcome
    }
}
