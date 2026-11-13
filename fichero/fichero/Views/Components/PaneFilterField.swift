import SwiftUI

/// The one Filter control of every bottom bar (`panes.chrome.one-filter-pattern`, owner 2026-11-13): a rounded field
/// with the filter icon and its chevron inside it, opening the pane's filter menu (what the list shows), then the text,
/// then a clear button while there is text. Never a second row, never the search loupe, never a separate button.
struct PaneFilterField<MenuContent: View>: View {
    @Binding var text: String
    var prompt = "Filter"
    var accessibilityID = "paneFilterField"
    @ViewBuilder var menu: () -> MenuContent

    /// The filter icon every bar shows, Xcode's navigator filter.
    static var symbol: String { "line.3.horizontal.decrease.circle" }

    var body: some View {
        HStack(spacing: 4) {
            Menu {
                menu()
            } label: {
                HStack(spacing: 1) {
                    Image(systemName: Self.symbol)
                    Image(systemName: "chevron.down").font(.system(size: 7, weight: .semibold))
                }
                .foregroundStyle(.secondary)
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("What this list shows")
            .accessibilityLabel("Filter options")
            TextField(prompt, text: $text)
                .textFieldStyle(.plain)
                .accessibilityIdentifier(accessibilityID)
            if !text.isEmpty {
                Button {
                    text = ""
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Clear filter")
                .accessibilityLabel("Clear filter")
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(.fill.tertiary, in: RoundedRectangle(cornerRadius: 6))
    }
}

/// The one Metadata button of every bottom bar (`panes.chrome.one-filter-pattern`): what each row shows about an item.
/// Present in every bar; its menu may be empty where a view has nothing to show yet.
struct PaneMetadataButton<MenuContent: View>: View {
    @ViewBuilder var menu: () -> MenuContent

    /// The Metadata icon every bar shows (the Items bar's row-attributes menu already used it).
    static var symbol: String { "switch.2" }

    var body: some View {
        Menu {
            menu()
        } label: {
            Image(systemName: Self.symbol)
        }
        .menuStyle(.button)
        .paneBarButtonStyle()
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Metadata: what each row shows")
        .accessibilityLabel("Metadata")
    }
}

#Preview("Filter field and Metadata") {
    @Previewable @State var text = ""
    HStack {
        PaneMetadataButton { Toggle("Item count", isOn: .constant(true)) }
        PaneFilterField(text: $text) { Toggle("Entities and Claims", isOn: .constant(true)) }
    }
    .padding()
    .frame(width: 320)
}
