import SwiftUI

// MARK: - Settings View

/// Main settings view with tabs for General, AI, and backend/system settings.
struct SettingsView: View {
    @Environment(AppState.self) var appState
    @ObservedObject var featureManager = FeatureManager.shared

    private var settingsSelection: Binding<SettingsTab> {
        Binding(
            get: { appState.selectedSettingsTab },
            set: { appState.selectedSettingsTab = $0 }
        )
    }

    var body: some View {
        TabView(selection: settingsSelection) {
            AISettingsView()
                .tag(SettingsTab.aiModels)
                .tabItem {
                    Label("AI", systemImage: "brain")
                }

            if featureManager.isMCPEnabled {
                MCPServersView()
                    .environment(appState.mcpService)
                    .tag(SettingsTab.mcp)
                    .tabItem {
                        Label("MCP", systemImage: "server.rack")
                    }
            }

            if featureManager.isIntegrationsEnabled {
                IntegrationsSettingsView(showAutomationRules: featureManager.isAutomationEnabled)
                    .tag(SettingsTab.integrations)
                    .tabItem {
                        Label("Integrations", systemImage: "app.connected.to.app.below.fill")
                    }
            }

            if featureManager.isSettingsGeneralTabEnabled {
                GeneralSettingsView()
                    .tag(SettingsTab.general)
                    .tabItem {
                        Label("General", systemImage: "gear")
                    }
            }

            #if canImport(AppKit)
            if featureManager.isSettingsEngineTabEnabled {
                EngineSettingsView()
                    .tag(SettingsTab.engine)
                    .tabItem {
                        Label("Engine", systemImage: "square.grid.3x1.below.line.grid.1x2")
                    }
            }

            if featureManager.isSettingsShareTabEnabled {
                ShareSettingsView()
                    .tag(SettingsTab.connect)
                    .tabItem {
                        Label("Connect", systemImage: "qrcode.viewfinder")
                    }
            }
            #endif

            if featureManager.isSettingsBackendTabEnabled {
                BackendSettingsView()
                    .tag(SettingsTab.backend)
                    .tabItem {
                        Label("Backend", systemImage: "server.rack")
                    }
            }

            if featureManager.isSettingsUsersTabEnabled {
                UsersSettingsView()
                    .tag(SettingsTab.users)
                    .tabItem {
                        Label("Users", systemImage: "person.2")
                    }
            }

            if featureManager.isSettingsCaptureTabEnabled {
                CaptureSettingsView()
                    .tag(SettingsTab.capture)
                    .tabItem {
                        Label("Capture", systemImage: "arrow.up.doc")
                    }
            }

            #if !canImport(AppKit)
            AboutView()
                .tag(SettingsTab.about)
                .tabItem {
                    Label("About", systemImage: "info.circle")
                }
            #endif

            AuditHistorySettingsTab()
                .tag(SettingsTab.history)
                .tabItem {
                    Label("History", systemImage: "clock.arrow.circlepath")
                }

            BackupsSettingsTab()
                .tag(SettingsTab.backups)
                .tabItem {
                    Label("Backups", systemImage: "externaldrive.badge.timemachine")
                }
        }
        .frame(width: 680, height: 520)
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
