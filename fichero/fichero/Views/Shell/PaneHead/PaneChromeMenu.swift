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
    @Environment(\.paneKindSwitcher) private var kindSwitcher
    @Environment(\.paneLeafId) private var leafId

    var body: some View {
        if splitActions != nil || isPinned != nil || onClose != nil || kindSwitcher != nil || leafId != nil {
            Menu {
                PaneMenuEntries(splitActions: splitActions, isPinned: isPinned, closeTitle: closeTitle, onClose: onClose)
            } label: {
                // The pane's own icon with a chevron, never a + (owner 2026-11-13), so the head still says what it shows.
                HStack(spacing: 2) {
                    Image(systemName: PaneMenuEntries.buttonIcon(kindSwitcher?.currentKind))
                    Image(systemName: "chevron.down").font(.caption2.weight(.semibold))
                }
                .foregroundStyle(Color.secondary)
            }
            .paneBarMenuStyle()
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pane menu")
            .accessibilityLabel("Pane menu")
        }
    }
}

/// The pane menu's rows, shared by the head's button and its right-click so both list the same entries in the
/// same order (`panes.chrome.one-pane-menu`): Pane ▸, Split, Focus on Pane, Pin, Close.
struct PaneMenuEntries: View {
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    var closeTitle: String?
    var onClose: (() -> Void)?
    @Environment(\.offersTranscriptionFont) private var offersFont
    @Environment(TranscriptionFontStore.self) private var fontStore: TranscriptionFontStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @Environment(\.paneKindSwitcher) private var kindSwitcher
    @Environment(\.paneLeafId) private var leafId
    @Environment(WindowState.self) private var windowState: WindowState?

    /// The menu button's glyph: the pane's kind icon; a generic pane glyph when the kind is not known.
    static func buttonIcon(_ kind: PaneSpec.Kind?) -> String { kind?.icon ?? "rectangle.split.2x1" }

    /// The Focus entry's title: Focus on Pane, or Leave Focus while this pane is the one in Focus.
    static func focusTitle(leaf: UUID?, focused: UUID?) -> String {
        leaf != nil && leaf == focused ? "Leave Focus" : "Focus on Pane"
    }

    var body: some View {
        if let kindSwitcher {
            Menu("Pane") {
                ForEach(PaneSpec.Kind.selectableKinds, id: \.rawValue) { kind in
                    Button { kindSwitcher.switchKind(kind) } label: {
                        // The current kind ticked, as the menu's other choices are.
                        Label(kind.title, systemImage: kind == kindSwitcher.currentKind ? "checkmark" : kind.icon)
                    }
                }
            }
            Divider()
        }
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
        if let leafId, let windowState {
            // ⌃⌘R from the keyboard; here for the pane it is chosen on (`panes.focus.any-pane-fills-the-screen`).
            Button {
                windowState.focusedPaneLeaf = windowState.focusedPaneLeaf == leafId ? nil : leafId
            } label: {
                Label(Self.focusTitle(leaf: leafId, focused: windowState.focusedPaneLeaf), systemImage: "viewfinder")
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
