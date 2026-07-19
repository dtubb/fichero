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
    /// Injected by the Settings scene (#3033/#3034) — the panes must not reach
    /// for the singleton themselves. @EnvironmentObject, not @Environment:
    /// FeatureManager is @AppStorage-backed and so must stay an
    /// ObservableObject until #3743 re-backs its flags on UserDefaults.
    @EnvironmentObject var featureManager: FeatureManager

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
                // General + AI at the top (the maintainer's top-of-list). Apple
                // System-Settings style: each row is a tinted rounded-rect glyph.
                Section {
                    if featureManager.isSettingsGeneralTabEnabled {
                        row(.general, "General", "gear", .gray)
                    }
                    row(.aiModels, "AI", "brain", .purple)
                }

                // Per-view settings (#3680) — Library is ONE surface (its icon /
                // column / list / canvas view modes are not separate tabs).
                Section("Views") {
                    row(.libraryView, "Library", "square.grid.2x2", .blue)
                    row(.previewView, "Preview", "sidebar.right", .teal)
                    row(.readerView, "Reader", "book", .orange)
                    row(.inspectorView, "Inspector", "slider.horizontal.3", .indigo)
                }

                // MCP servers = the tool config for the agentic surface (chat +
                // research + agents). Integrations is dropped — its pane is
                // placeholder-only; it returns under Workflows when real.
                if featureManager.isMCPEnabled {
                    Section("Agents") {
                        row(.mcp, "MCP", "server.rack", .green)
                    }
                }

                Section("System") {
                    // Engine (multi-user toggle, restart, stats) + Sharing
                    // (People / Devices+QR / Capture) hold real, keepable capabilities.
                    // Their EXISTENCE must not hang off per-feature migration flags —
                    // those are `.alpha`-tier, so both vanished for beta testers, which
                    // is why the user had "nowhere to turn on the qrcode" and no way to
                    // enable multi-user to share with people (#3811/#3776). Reachable
                    // for internal + tester builds; still hidden in release until the
                    // fail-closed engine-refusal P0 lands (#3776).
                    if Self.showsTesterSettingsPane(tier: featureManager.activeBuildTier) {
                        row(.engine, "Engine", "square.grid.3x1.below.line.grid.1x2", .gray)
                        row(.connect, "Sharing", "person.2.badge.gearshape", .blue)
                    }
                }

                Section {
                    row(.history, "History", "clock.arrow.circlepath", .brown)
                    row(.backups, "Snapshots", "externaldrive.badge.timemachine", .green)
                    #if !canImport(AppKit)
                    row(.about, "About", "info.circle", .gray)
                    #endif
                }
            }
            .navigationTitle("Settings")
            .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 280)
            // The section list is the only navigation between panes, and this view
            // deliberately mimics macOS System Settings — whose source list is never
            // collapsible. Drop the automatic sidebar-toggle so the list can't be
            // hidden into a navigation dead end (#3812). Scoped to this split view,
            // so the main window's sidebar toggle is untouched.
            .toolbar(removing: .sidebarToggle)
        } detail: {
            detail(for: appState.selectedSettingsTab)
        }
        .frame(minWidth: 720, idealWidth: 720, minHeight: 520, idealHeight: 520)
    }

    /// One sidebar source-list row, tagged by its destination tab so
    /// `List(selection:)` drives `appState.selectedSettingsTab`. Its icon is a
    /// tinted rounded-rect glyph in the macOS System-Settings style.
    private func row(_ tab: SettingsTab, _ title: LocalizedStringKey,
                     _ symbol: String, _ tint: Color) -> some View {
        Label(title, systemImage: symbol)
            .tag(tab)
            .labelStyle(SettingsRowIconStyle(tint: tint))
    }

    /// A white SF Symbol on a tinted rounded rectangle — the System-Settings
    /// sidebar icon look (one tint per row).
    private struct SettingsRowIconStyle: LabelStyle {
        let tint: Color
        func makeBody(configuration: Configuration) -> some View {
            Label {
                configuration.title
            } icon: {
                configuration.icon
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 20, height: 20)
                    .background(RoundedRectangle(cornerRadius: 5, style: .continuous).fill(tint))
            }
        }
    }

    /// Whether the Engine & Access panes (Engine/Backend and Library Access —
    /// People / Devices+QR / Capture) are reachable in this build. They hold real,
    /// keepable capabilities (the multi-user toggle, device pairing + QR, users),
    /// so their existence must NOT depend on a per-feature migration flag — those
    /// flags are `.alpha`-tier, so in a beta build the sharing/QR pane vanished and
    /// the user had "nowhere to turn on the qrcode" (and no way to enable multi-user
    /// to share with people) — #3811/#3776. Reachable in internal + tester builds;
    /// still hidden in release until the fail-closed engine-refusal P0 is verified
    /// (#3776). When that lands, this gate goes too and the panes are simply always
    /// on — turning a capability on is one action, never "enable the subsystem first".
    static func showsTesterSettingsPane(tier: FeatureTier) -> Bool {
        tier != .release
    }

    // A flat tab → pane dispatch; its cyclomatic complexity is inherent to the
    // number of settings sections, not branching logic — hence the region disable.
    // swiftlint:disable cyclomatic_complexity
    /// The detail pane for the selected tab — the existing view, unchanged. The
    /// grouped tabs (engine/backend, connect/users/capture) resolve to their
    /// #3396 group container.
    @ViewBuilder
    private func detail(for tab: SettingsTab) -> some View {
        switch tab {
        case .libraryView:
            LibraryViewSettingsPane()
        case .previewView:
            PreviewViewSettingsPane()
        case .readerView:
            ReaderViewSettingsPane()
        case .inspectorView:
            InspectorViewSettingsPane()
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
            SharingSettingsView()
        case .about:
            #if !canImport(AppKit)
            AboutView()
            #else
            EmptyView()
            #endif
        case .history:
            AuditHistorySettingsTab()
        case .backups:
            SnapshotsSettingsTab()
        }
    }
    // swiftlint:enable cyclomatic_complexity
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
            // The panes bind @EnvironmentObject now, so the preview must inject it
            // exactly as the real Settings scene does — otherwise the preview traps.
            .environmentObject(FeatureManager.shared)
    }
}
