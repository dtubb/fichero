import SwiftUI

/// A tab/section usable in the shared ``SurfaceTabBar`` (#3530). The Reader,
/// Document Inspector, Workflow, Chat, Research, and Search surfaces make their
/// top-level tab enums conform so the whole app shares ONE top-tab chrome
/// instead of each re-implementing it. Reuse, don't re-implement.
protocol SurfaceTab: Identifiable, Hashable {
    /// Display + accessibility label.
    var title: String { get }
    /// SF Symbol shown in the icon row.
    var icon: String { get }
    /// Tooltip: what the tab is / does.
    var help: String { get }
    /// Stable per-tab XCUITest hook.
    var accessibilityID: String { get }
}

extension SurfaceTab {
    /// Default a11y id derived from the title; adopters override to keep an
    /// existing hook (e.g. the inspector's `inspectorSection-Source`).
    var accessibilityID: String { "surfaceTab-\(title)" }
}

/// The app's shared top tab bar (#3530): a row of labelled icon buttons with a
/// per-segment tooltip + accessibility hook and the Tahoe glass strip, extracted
/// verbatim from the Inspector `sectionBar` (Daniel's chosen icon-row switcher).
///
/// Icon-only (not a `.segmented` Picker) so each button keeps its own `.help`
/// and `.accessibilityIdentifier`, and 3–5 facets stay legible across compact
/// widths. The active tab gets the accent fill + tint; dividers adjacent to the
/// active tab hide, matching the inspector look. Surfaces adopt this instead of
/// bespoke tab bars so they read as one system.
struct SurfaceTabBar<Tab: SurfaceTab>: View {
    let tabs: [Tab]
    @Binding var selection: Tab
    /// Container XCUITest hook. Defaults to `surfaceTabBar`; adopters override to
    /// preserve an existing hook (e.g. the inspector's `inspectorSectionBar`).
    var accessibilityID: String = "surfaceTabBar"

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(tabs.enumerated()), id: \.element) { index, tab in
                if index > 0 {
                    Divider()
                        .frame(height: 14)
                        .opacity(hidesDivider(before: index) ? 0 : 1)
                }
                tabButton(tab)
            }
        }
        .frame(maxWidth: .infinity)
        .surfaceGlassStrip()
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
        .accessibilityIdentifier(accessibilityID)
    }

    /// Hide the divider adjacent to the active tab (matches the inspector look).
    private func hidesDivider(before index: Int) -> Bool {
        selection == tabs[index] || selection == tabs[index - 1]
    }

    @ViewBuilder
    private func tabButton(_ tab: Tab) -> some View {
        let isActive = selection == tab
        Button {
            selection = tab
        } label: {
            Label(tab.title, systemImage: tab.icon)
                .labelStyle(.iconOnly)
                .font(.title3)
                .frame(maxWidth: .infinity, minHeight: 30)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(tab.title)
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(isActive ? Color.accentColor.opacity(0.18) : Color.clear)
                .padding(2)
        )
        .foregroundStyle(isActive ? Color.accentColor : Color.secondary)
        .help(tab.help)
        .accessibilityIdentifier(tab.accessibilityID)
    }
}

// MARK: - Shared chrome glass strip

extension View {
    /// The shared chrome-strip glass treatment (#3061/#3530), generalized from
    /// `inspectorGlassStrip` so every surface's chrome matches.
    func surfaceGlassStrip() -> some View {
        modifier(SurfaceGlassStrip())
    }
}

private struct SurfaceGlassStrip: ViewModifier {
    func body(content: Content) -> some View {
        #if os(visionOS)
        content
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        #else
        GlassEffectContainer {
            content
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
        }
        #endif
    }
}
