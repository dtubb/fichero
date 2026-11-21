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
    var viewAs: AnyView?
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    var closeTitle: String?
    var onClose: (() -> Void)?
    @Environment(\.paneKindSwitcher) private var kindSwitcher
    @Environment(\.paneLeafId) private var leafId

    var body: some View {
        if viewAs != nil || splitActions != nil || isPinned != nil || onClose != nil || kindSwitcher != nil || leafId != nil {
            Menu {
                PaneMenuEntries(
                    viewAs: viewAs, splitActions: splitActions, isPinned: isPinned, closeTitle: closeTitle, onClose: onClose
                )
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
/// same order (`panes.chrome.one-pane-menu`): Pane ▸, View As ▸, Split Right ▸, Split Below ▸, Focus on Pane, Pin, Close.
struct PaneMenuEntries: View {
    /// View As ▸, the pane's own views (`PaneViewChooser`); nil for a head without a view chooser.
    var viewAs: AnyView?
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
        }
        if let viewAs { viewAs }
        if kindSwitcher != nil || viewAs != nil { Divider() }
        if let actions = splitActions {
            // Each a submenu of kinds: splitting ADDS that pane beside or below in one step (`panes.head.one-menu-button`).
            Menu("Split Right") {
                ForEach(PaneSpec.Kind.selectableKinds, id: \.rawValue) { kind in
                    Button { actions.onSplitRight(kind) } label: { Label(kind.title, systemImage: kind.icon) }
                }
            }
            Menu("Split Below") {
                ForEach(PaneSpec.Kind.selectableKinds, id: \.rawValue) { kind in
                    Button { actions.onSplitBelow(kind) } label: { Label(kind.title, systemImage: kind.icon) }
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
            // Checked while pinned (`panes.head.one-menu-button`); the head has no pin button of its own.
            Toggle(isOn: isPinned) {
                Label("Pin Pane", systemImage: "pin")
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
