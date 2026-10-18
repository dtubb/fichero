import SwiftUI

/// The pane head's SPLIT control (Daniel, 2026-08-23: the "+" that lets us
/// "split it vertical, horizontal").
///
/// It carried the pin row too until 2026-09-02, when Daniel reported that
/// with splits open "there is no way to pin a pane to what it currently
/// shows": pinning is a MODE the pane is in, and a mode needs a control that
/// shows its state closed. The pin is now a one-click toggle in `PaneHead`
/// beside this menu; this stays the additive split menu it is named for.
///
/// `panes.chrome.one-pane-menu` (#5435): this is now the pane menu. Its entries (`PaneMenuEntries`) are
/// split, pin and close, and the head's right-click shows the same list. Show In This Pane, View and
/// What to Show join them as each kind hands its closures to the head.
///
/// Renders from what the pane actually has: split actions arrive via the head's environment, the pin
/// and close from the head itself; with none, nothing renders.
private struct OffersTranscriptionFontKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// Whether this pane draws transcription text, so its menu offers the Font choice (#5438).
    var offersTranscriptionFont: Bool {
        get { self[OffersTranscriptionFontKey.self] }
        set { self[OffersTranscriptionFontKey.self] = newValue }
    }
}

struct PaneChromeMenu: View {
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    var closeTitle: String?
    var onClose: (() -> Void)?

    var body: some View {
        if splitActions != nil || isPinned != nil || onClose != nil {
            Menu {
                PaneMenuEntries(splitActions: splitActions, isPinned: isPinned, closeTitle: closeTitle, onClose: onClose)
            } label: {
                Image(systemName: "plus")
                    .foregroundStyle(Color.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pane menu")
            .accessibilityLabel("Pane menu")
        }
    }
}

/// The pane menu's rows, shared by the head's + and its right-click so both list the same entries in the
/// same order: Split, Pin, Close.
struct PaneMenuEntries: View {
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    var closeTitle: String?
    var onClose: (() -> Void)?
    @Environment(\.offersTranscriptionFont) private var offersFont
    @Environment(TranscriptionFontStore.self) private var fontStore: TranscriptionFontStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    var body: some View {
        if let actions = splitActions {
            // ADDITIONS only (Daniel, 2026-08-23): the "+" never
            // removes a split — the pane's X collapses it. A row
            // shows only while its toggle ADDS: thirds are a
            // single-axis affair, so a 2×2 grid offers neither.
            let grid = actions.hasVertical && actions.hasHorizontal
            if actions.verticalCount == 1 || (actions.verticalCount == 2 && !grid) {
                Button {
                    actions.onToggleVertical()
                } label: {
                    Label(
                        actions.hasVertical ? "Add Third Vertical Pane" : "Split Vertical",
                        systemImage: ToolbarSymbols.splitVertical
                    )
                }
            }
            if actions.horizontalCount == 1 || (actions.horizontalCount == 2 && !grid) {
                Button {
                    actions.onToggleHorizontal()
                } label: {
                    Label(
                        actions.hasHorizontal ? "Add Third Horizontal Pane" : "Split Horizontal",
                        systemImage: ToolbarSymbols.splitHorizontal
                    )
                }
            }
        }
        if let isPinned {
            Button {
                isPinned.wrappedValue.toggle()
            } label: {
                Label(isPinned.wrappedValue ? "Unpin Pane" : "Pin Pane",
                      systemImage: isPinned.wrappedValue ? "pin.slash" : "pin")
            }
        }
        if offersFont, let fontStore {
            Divider()
            Menu("Font") {
                Button("Automatic") { Task { await fontStore.choose(nil, steps: windowSteps) } }
                ForEach(BundledFonts.shared.familyNames, id: \.self) { name in
                    Button {
                        Task { await fontStore.choose(name, steps: windowSteps) }
                    } label: {
                        if fontStore.family == name { Label(name, systemImage: "checkmark") } else { Text(name) }
                    }
                }
            }
        }
        if let onClose, let closeTitle {
            Divider()
            Button(role: .destructive, action: onClose) {
                Label(closeTitle, systemImage: "xmark")
            }
        }
    }
}
