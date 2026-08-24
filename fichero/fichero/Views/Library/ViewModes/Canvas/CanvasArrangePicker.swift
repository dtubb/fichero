import SwiftUI

// MARK: - The one picker that moves cards (§20.3, R10)

/// "Arrange by", in both canvases' control strips.
///
/// ONE control, shared, reading ONE persisted key — the same discipline as the
/// shared column derivation and for the same reason: 2D and 3D share a layout
/// store, so a board they disagree about is two different boards. Switching
/// arrangement in the Canvas and finding Space still As Filed would be exactly
/// the "nothing stays where I put it" complaint, one level up.
///
/// §20.3's strip is eventually four pickers — Arrange, Depth, Colour by,
/// Highlight — of which only this one moves anything. The other three re-encode
/// in place and are their own channels; Highlight already ships as
/// `CanvasEmphasis`.
struct CanvasArrangePicker: View {
    /// The control OWNS the persisted choice; the canvases only read it. One
    /// writer, two readers, one key — nothing to keep in sync by hand.
    @AppStorage(CanvasArrangement.storageKey) private var raw = CanvasArrangement.asFiled.rawValue

    private var arrangement: Binding<CanvasArrangement> {
        Binding(get: { CanvasArrangement.stored(raw) }, set: { raw = $0.rawValue })
    }

    var body: some View {
        Menu {
            Picker("Arrange by", selection: arrangement) {
                ForEach(CanvasArrangement.allCases) { option in
                    Label(option.label, systemImage: option.icon).tag(option)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: "square.grid.2x2")
        }
        .fixedSize()
        .accessibilityLabel("Arrange by")
        .help("Arrange by \(arrangement.wrappedValue.label)")
    }
}

/// The persisted choice, so both canvases read the SAME value and it survives
/// a relaunch. A view-level preference, matching the `@AppStorage` house
/// pattern for toolbar state (ReaderToolbar) rather than inventing a store for
/// one enum.
extension CanvasArrangement {
    static let storageKey = "fichero.canvas.arrangement"

    /// Decode a persisted raw value, falling back to the default board rather
    /// than to a crash or an empty canvas if the key is stale or absent.
    static func stored(_ rawValue: String) -> CanvasArrangement {
        CanvasArrangement(rawValue: rawValue) ?? .asFiled
    }
}

// MARK: - The control strip

/// §20.3's control strip: the pickers that decide what the board says.
///
/// One view, used by BOTH canvases, so a control cannot exist in one and not
/// the other. Two of the four today — Arrange (moves cards) and Colour by
/// (never does); Depth joins when z has a second variable to carry, and
/// Highlight when an entity picker lands on top of `CanvasEmphasis`.
struct CanvasControlStrip: View {
    var body: some View {
        HStack(spacing: 6) {
            CanvasArrangePicker()
            CanvasColourPicker()
        }
    }
}

/// The strip's overflow-menu mirror (2026-08-24): at narrow widths the
/// channels used to vanish entirely — the missing half of the one-bottom-bar
/// rule. Same pickers, titled, as submenus.
struct CanvasControlStripMenu: View {
    @AppStorage(CanvasArrangement.storageKey) private var arrangementRaw = CanvasArrangement.asFiled.rawValue

    var body: some View {
        Menu("Arrange By") {
            Picker("", selection: Binding(
                get: { CanvasArrangement.stored(arrangementRaw) },
                set: { arrangementRaw = $0.rawValue }
            )) {
                ForEach(CanvasArrangement.allCases) { option in
                    Label(option.label, systemImage: option.icon).tag(option)
                }
            }
            .pickerStyle(.inline)
        }
        CanvasColourPickerMenu()
    }
}
