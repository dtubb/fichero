import SwiftUI

// MARK: - Section metadata (title / symbol / tint)

/// The title, SF Symbol, and tint for one `SettingsTab` — the single source of
/// truth both the sidebar rows (`SettingsView.row`) and the detail-pane
/// header/orientation-header read, so the two never drift out of sync.
struct SettingsSectionInfo {
    let title: LocalizedStringKey
    let symbol: String
    let tint: Color

    // One case per `SettingsTab`; the branching is inherent to the number of
    // settings sections, not real logic, hence the same disable the existing
    // `SettingsView.detail(for:)` switch uses.
    // swiftlint:disable:next cyclomatic_complexity
    static func info(for tab: SettingsTab) -> SettingsSectionInfo {
        switch tab {
        case .general:
            return SettingsSectionInfo(title: "General", symbol: "gear", tint: .gray)
        case .aiModels:
            return SettingsSectionInfo(title: "AI", symbol: "brain", tint: .purple)
        case .libraryView:
            return SettingsSectionInfo(title: "Library", symbol: "square.grid.2x2", tint: .blue)
        case .previewView:
            return SettingsSectionInfo(title: "Preview", symbol: "sidebar.right", tint: .teal)
        case .readerView:
            return SettingsSectionInfo(title: "Reader", symbol: "book", tint: .orange)
        case .inspectorView:
            return SettingsSectionInfo(title: "Inspector", symbol: "slider.horizontal.3", tint: .indigo)
        case .mcp:
            return SettingsSectionInfo(title: "MCP", symbol: "server.rack", tint: .green)
        case .integrations:
            return SettingsSectionInfo(title: "Integrations", symbol: "puzzlepiece.extension", tint: .gray)
        case .engine, .backend:
            return SettingsSectionInfo(
                title: "Server", symbol: "square.grid.3x1.below.line.grid.1x2", tint: .gray
            )
        case .connect, .users, .capture:
            return SettingsSectionInfo(title: "Sharing", symbol: "person.2.badge.gearshape", tint: .blue)
        case .about:
            return SettingsSectionInfo(title: "About", symbol: "info.circle", tint: .gray)
        case .history:
            return SettingsSectionInfo(title: "History", symbol: "clock.arrow.circlepath", tint: .brown)
        case .backups:
            return SettingsSectionInfo(
                title: "Snapshots", symbol: "externaldrive.badge.timemachine", tint: .green
            )
        }
    }
}

// MARK: - Back / forward history

/// Back/forward navigation history for the Settings detail pane, mirroring
/// macOS System Settings' top-left chevrons. A back-stack + forward-stack of
/// previously-viewed sections, driven by `SettingsView` observing
/// `appState.selectedSettingsTab`.
///
/// `goBack`/`goForward` set `isNavigatingProgrammatically` BEFORE applying the
/// tab change, but deliberately do NOT reset it themselves: SwiftUI's
/// `onChange(of:)` fires asynchronously on the next update pass, not
/// synchronously inside the property set, so resetting the flag right after
/// `apply()` would race the very `onChange` it's meant to guard (the flag
/// would already be back to `false` by the time `recordSelection` runs, and
/// the programmatic move would be miscounted as a fresh navigation). Instead
/// `recordSelection` — called from that `onChange` — consumes and clears the
/// flag itself, so it stays `true` no matter how long SwiftUI takes to notice.
@Observable
final class SettingsNavigationHistory {
    private(set) var backStack: [SettingsTab] = []
    private(set) var forwardStack: [SettingsTab] = []
    private var isNavigatingProgrammatically = false

    var canGoBack: Bool { !backStack.isEmpty }
    var canGoForward: Bool { !forwardStack.isEmpty }

    /// Called from `SettingsView`'s `onChange(of: appState.selectedSettingsTab)`
    /// with the tab being navigated AWAY from. A normal (sidebar or
    /// programmatic `openSettings`) selection pushes it onto the back-stack and
    /// clears any forward history; a back/forward-triggered selection is
    /// swallowed instead.
    func recordSelection(from previousTab: SettingsTab) {
        guard !isNavigatingProgrammatically else {
            isNavigatingProgrammatically = false
            return
        }
        backStack.append(previousTab)
        forwardStack.removeAll()
    }

    /// Pops the most recent back entry, pushes `current` onto the
    /// forward-stack, and applies the popped tab via `apply`.
    func goBack(current: SettingsTab, apply: (SettingsTab) -> Void) {
        guard let target = backStack.popLast() else { return }
        forwardStack.append(current)
        isNavigatingProgrammatically = true
        apply(target)
    }

    /// Pops the most recent forward entry, pushes `current` back onto the
    /// back-stack, and applies the popped tab via `apply`.
    func goForward(current: SettingsTab, apply: (SettingsTab) -> Void) {
        guard let target = forwardStack.popLast() else { return }
        backStack.append(current)
        isNavigatingProgrammatically = true
        apply(target)
    }
}

// MARK: - Detail header (back/forward + title)

/// The top-of-detail-pane header: back/forward chevrons in a rounded capsule
/// followed by the section title — matching macOS System Settings' top-left
/// navigation control. Generous top padding keeps it out of the traffic-light
/// area, matching System Settings' inset.
struct SettingsDetailHeader: View {
    let tab: SettingsTab
    let history: SettingsNavigationHistory
    let onNavigate: (SettingsTab) -> Void

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 0) {
                Button {
                    history.goBack(current: tab, apply: onNavigate)
                } label: {
                    Image(systemName: "chevron.left")
                        .frame(width: 24, height: 22)
                }
                .disabled(!history.canGoBack)
                .help("Back")
                .accessibilityLabel("Back")

                Divider().frame(height: 12)

                Button {
                    history.goForward(current: tab, apply: onNavigate)
                } label: {
                    Image(systemName: "chevron.right")
                        .frame(width: 24, height: 22)
                }
                .disabled(!history.canGoForward)
                .help("Forward")
                .accessibilityLabel("Forward")
            }
            .buttonStyle(.plain)
            .font(.body.weight(.semibold))
            .background(.quaternary, in: Capsule())

            Text(SettingsSectionInfo.info(for: tab).title)
                .font(.title2.weight(.semibold))

            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.top, 24)
        .padding(.bottom, 8)
    }
}

// MARK: - Orientation header (icon + name atop the content)

/// Repeats the selected section's colored icon + name at the top of the
/// pane's CONTENT, above its settings rows — the same orientation cue macOS
/// System Settings shows atop e.g. the Wi-Fi pane (Wi-Fi icon + "Wi-Fi").
struct SettingsSectionOrientationHeader: View {
    let tab: SettingsTab

    var body: some View {
        let info = SettingsSectionInfo.info(for: tab)
        HStack(spacing: 10) {
            Image(systemName: info.symbol)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(info.tint))
            Text(info.title)
                .font(.title3.weight(.semibold))
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 12)
    }
}
