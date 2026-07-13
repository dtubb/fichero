import SwiftUI

// MARK: - Settings View

/// Main settings view: a macOS System-Settings-style sidebar (source list →
/// detail), replacing the former top-tab `TabView` (#3679). One
/// `NavigationSplitView` serves every platform — on iPhone/iPad it collapses to
/// a `NavigationStack` list → detail push. Every detail pane is the SAME
/// existing view (incl. the #3396 Engine / Library-Access group containers);
/// this is a container restructure, not a rewrite of any pane.
struct SettingsView: View {
    @Environment(AppState.self) var appState
    @ObservedObject var featureManager = FeatureManager.shared

    /// Sidebar single-selection. `List(selection:)` wants an optional; a nil
    /// selection (rare) falls back to the AI pane rather than a blank detail.
    private var sidebarSelection: Binding<SettingsTab?> {
        Binding(
            get: { appState.selectedSettingsTab },
            set: { appState.selectedSettingsTab = $0 ?? .aiModels }
        )
    }

    var body: some View {
        NavigationSplitView {
            List(selection: sidebarSelection) {
                Section("Services") {
                    row(.aiModels, "AI", "brain")
                    if featureManager.isMCPEnabled {
                        row(.mcp, "MCP", "server.rack")
                    }
                    if featureManager.isIntegrationsEnabled {
                        row(.integrations, "Integrations", "app.connected.to.app.below.fill")
                    }
                }

                Section("Engine & Access") {
                    // Engine group (#3396): Backend folded in as a sub-section.
                    if featureManager.isSettingsEngineTabEnabled || featureManager.isSettingsBackendTabEnabled {
                        row(.engine, "Engine", "square.grid.3x1.below.line.grid.1x2")
                    }
                    // Library Access group (#3396): Connect + Users + Capture consolidated.
                    if featureManager.isSettingsShareTabEnabled
                        || featureManager.isSettingsUsersTabEnabled
                        || featureManager.isSettingsCaptureTabEnabled {
                        row(.connect, "Library Access", "lock.shield")
                    }
                }

                Section("App") {
                    if featureManager.isSettingsGeneralTabEnabled {
                        row(.general, "General", "gear")
                    }
                    row(.history, "History", "clock.arrow.circlepath")
                    row(.backups, "Backups", "externaldrive.badge.timemachine")
                    #if !canImport(AppKit)
                    row(.about, "About", "info.circle")
                    #endif
                }
            }
            .navigationTitle("Settings")
            .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 280)
        } detail: {
            detail(for: appState.selectedSettingsTab)
        }
        .frame(minWidth: 720, idealWidth: 720, minHeight: 520, idealHeight: 520)
    }

    /// One sidebar source-list row, tagged by its destination tab so
    /// `List(selection:)` drives `appState.selectedSettingsTab`.
    private func row(_ tab: SettingsTab, _ title: LocalizedStringKey, _ symbol: String) -> some View {
        Label(title, systemImage: symbol).tag(tab)
    }

    /// The detail pane for the selected tab — the existing view, unchanged. The
    /// grouped tabs (engine/backend, connect/users/capture) resolve to their
    /// #3396 group container.
    @ViewBuilder
    private func detail(for tab: SettingsTab) -> some View {
        switch tab {
        case .aiModels:
            AISettingsView()
        case .mcp:
            MCPServersView()
                .environment(appState.mcpService)
        case .integrations:
            IntegrationsSettingsView(showAutomationRules: featureManager.isAutomationEnabled)
        case .general:
            GeneralSettingsView()
        case .engine, .backend:
            EngineGroupSettingsView()
        case .connect, .users, .capture:
            LibraryAccessSettingsView()
        case .about:
            #if !canImport(AppKit)
            AboutView()
            #else
            EmptyView()
            #endif
        case .history:
            AuditHistorySettingsTab()
        case .backups:
            BackupsSettingsTab()
        }
    }
}

// MARK: - Consolidated Settings Groups (#3396)

/// A sub-section within a consolidated settings tab. `label` names its segment.
private protocol SettingsGroupSection: Identifiable, Hashable {
    var label: String { get }
}

/// Shared chrome for a consolidated settings tab: a segmented sub-picker over the
/// available sub-sections (hidden when only one is available), then the selected
/// section's EXISTING settings view — every reused pane is unchanged (#3396). The
/// selection is clamped to what's available so a default that a platform/flag
/// hides (e.g. the macOS-only Engine/Devices panes on iOS) never shows blank.
private struct SettingsGroupContainer<Section: SettingsGroupSection, Content: View>: View {
    let sections: [Section]
    @Binding var rawSelection: Section
    @ViewBuilder let content: (Section) -> Content

    private var effective: Section {
        sections.contains(rawSelection) ? rawSelection : (sections.first ?? rawSelection)
    }

    var body: some View {
        VStack(spacing: 0) {
            if sections.count > 1 {
                Picker("", selection: Binding(get: { effective }, set: { rawSelection = $0 })) {
                    ForEach(sections) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding()
                Divider()
            }
            content(effective)
        }
    }
}

private enum EngineGroupSection: String, CaseIterable, SettingsGroupSection {
    case engine = "Engine"
    case backend = "Backend"
    var id: String { rawValue }
    var label: String { rawValue }
}

/// Engine tab (#3396): folds the former Backend tab in as a sub-section. Reuses
/// EngineSettingsView + BackendSettingsView unchanged.
private struct EngineGroupSettingsView: View {
    @ObservedObject private var featureManager = FeatureManager.shared
    @State private var selection: EngineGroupSection = .engine

    private var availableSections: [EngineGroupSection] {
        var sections: [EngineGroupSection] = []
        #if canImport(AppKit)
        if featureManager.isSettingsEngineTabEnabled { sections.append(.engine) }
        #endif
        if featureManager.isSettingsBackendTabEnabled { sections.append(.backend) }
        return sections
    }

    var body: some View {
        SettingsGroupContainer(sections: availableSections, rawSelection: $selection) { section in
            switch section {
            case .engine:
                #if canImport(AppKit)
                EngineSettingsView()
                #endif
            case .backend:
                BackendSettingsView()
            }
        }
    }
}

private enum LibraryAccessSection: String, CaseIterable, SettingsGroupSection {
    case people = "People"
    case devices = "Devices"
    case capture = "Capture"
    var id: String { rawValue }
    var label: String { rawValue }
}

/// Library Access tab (#3396): who/what can reach a library — the former Connect
/// (device pairing / QR), Users (people/roles), and Capture (capture permissions)
/// tabs, consolidated. Reuses each pane unchanged.
private struct LibraryAccessSettingsView: View {
    @ObservedObject private var featureManager = FeatureManager.shared
    @State private var selection: LibraryAccessSection = .people

    private var availableSections: [LibraryAccessSection] {
        var sections: [LibraryAccessSection] = []
        if featureManager.isSettingsUsersTabEnabled { sections.append(.people) }
        #if canImport(AppKit)
        if featureManager.isSettingsShareTabEnabled { sections.append(.devices) }
        #endif
        if featureManager.isSettingsCaptureTabEnabled { sections.append(.capture) }
        return sections
    }

    var body: some View {
        SettingsGroupContainer(sections: availableSections, rawSelection: $selection) { section in
            switch section {
            case .people:
                UsersSettingsView()
            case .devices:
                #if canImport(AppKit)
                ShareSettingsView()
                #endif
            case .capture:
                CaptureSettingsView()
            }
        }
    }
}

// MARK: - Preview / Regression Guard (#2051)

/// Constructs the full settings root with the SAME environment objects the
/// real `Settings` scene injects (`appState` + `libraryManager`). Because
/// `TabView` builds every tab eagerly, rendering this preview exercises each
/// pane's construct path — so any settings pane that reads an @EnvironmentObject
/// NOT injected here (the exact bug behind #2051, where the Models tab's
/// LibraryManager dependency was missing from the Settings scene) traps on
/// render. Keep this preview's injected objects in sync with the `Settings`
/// scene in `FicheroApp.swift`; a divergence here is the regression signal.
#Preview("Settings (all panes)") {
    SettingsPreviewHarness()
}

/// Forces every gated settings tab on (so the preview covers the full surface,
/// not just the always-on Defaults tab) and injects the same environment
/// objects the real `Settings` scene does. The flag flip lives in `init` so the
/// preview body stays a clean single-expression `@ViewBuilder`.
private struct SettingsPreviewHarness: View {
    init() {
        FeatureManager.shared.allFeaturesEnabled = true
    }

    var body: some View {
        SettingsView()
            .environment(AppState())
            .environment(EmbeddedBackendService())
            .environment(LibraryManager.shared)
    }
}

private struct IntegrationsSettingsView: View {
    let showAutomationRules: Bool

    var body: some View {
        Form {
            Section {
                IntegrationsPlaceholderContent(
                    title: "Folder Watchers",
                    description: "Automatically process files when added to watched folders.",
                    icon: "folder.badge.gearshape"
                )
            }

            Section {
                IntegrationsPlaceholderContent(
                    title: "App Observers",
                    description: "Trigger workflows based on app events, like files saved from specific apps.",
                    icon: "app.badge"
                )
            }

            if showAutomationRules {
                Section {
                    IntegrationsPlaceholderContent(
                        title: "Automation Rules",
                        description: "Create rules to automatically organize and process documents.",
                        icon: "gearshape.2"
                    )
                }
            }
        }
        .formStyle(.grouped)
    }
}
