import SwiftUI

// MARK: - Colour by — the picker, and what it can colour by (§20.3)

/// Which document attribute the colour channel encodes.
///
/// Four honest cases. §20.3's wish-list also names date, star and prototype;
/// those are not on `Document` (or not yet dated — build-order step 8), and a
/// picker offering an attribute it cannot colour by is a menu that lies.
///
/// **EXTENSION POINT.** A new attribute is a case plus a line in
/// `value(for:in:)` — never a second colour path in a renderer. Colour is
/// assigned from the attribute VALUE by `CanvasTint`, so a new case inherits
/// stability, the shared palette, and both canvases for free.
enum CanvasColourBy: String, CaseIterable, Identifiable, Sendable {
    /// Every card keeps its kind tint — which IS a colour-by, just the default
    /// one, and the reason this is "off" rather than "no colour".
    ///
    /// Spelled `off`, not `none`: a case named `none` on a non-optional enum
    /// shadows `Optional.none` at every `.none` site, and the compiler resolves
    /// it silently either way. The bug that produces is unreadable.
    case off
    /// The card's parent folder: what a whole-library board is mostly asking.
    case folder
    /// Document kind (folder / page / image / …).
    case type
    /// Import and processing state — pending, processing, completed, failed.
    case status

    var id: String { rawValue }

    var label: String {
        switch self {
        case .off: "None"
        case .folder: "Folder"
        case .type: "Type"
        case .status: "Status"
        }
    }

    var icon: String {
        switch self {
        case .off: "circle.slash"
        case .folder: "folder"
        case .type: "doc"
        case .status: "circle.badge.checkmark"
        }
    }

    /// The attribute value this mode reads off a document, or nil to leave the
    /// card at its kind tint. One place, so the renderers never learn what a
    /// document is.
    func value(for document: Document) -> String? {
        switch self {
        case .off: nil
        case .folder: document.parentId
        case .type: document.docType.rawValue
        case .status: document.status.rawValue
        }
    }

    static let storageKey = "fichero.canvas.colourBy"

    /// Decode a persisted raw value, falling back to no colouring rather than
    /// to a crash or a board painted by a mode that no longer exists.
    static func stored(_ rawValue: String) -> CanvasColourBy {
        CanvasColourBy(rawValue: rawValue) ?? .off
    }
}

/// "Colour by", in both canvases' control strips — the §20.3 picker that
/// re-encodes without moving anything (§13.2).
///
/// Owns the persisted choice for the same reason `CanvasArrangePicker` does:
/// one writer, two readers, one key, so 2D and 3D cannot show the same board in
/// different colours.
struct CanvasColourPicker: View {
    @AppStorage(CanvasColourBy.storageKey) private var raw = CanvasColourBy.off.rawValue

    private var colourBy: Binding<CanvasColourBy> {
        Binding(get: { CanvasColourBy.stored(raw) }, set: { raw = $0.rawValue })
    }

    var body: some View {
        Menu {
            Picker("Colour by", selection: colourBy) {
                ForEach(CanvasColourBy.allCases) { option in
                    Label(option.label, systemImage: option.icon).tag(option)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: "paintpalette")
        }
        .fixedSize()
        .accessibilityLabel("Colour by")
        .help("Colour by \(colourBy.wrappedValue.label)")
    }
}

/// Titled overflow-submenu twin of `CanvasColourPicker` — same key, same rows.
struct CanvasColourPickerMenu: View {
    @AppStorage(CanvasColourBy.storageKey) private var raw = CanvasColourBy.off.rawValue

    var body: some View {
        Menu("Colour By") {
            Picker("", selection: Binding(
                get: { CanvasColourBy.stored(raw) }, set: { raw = $0.rawValue }
            )) {
                ForEach(CanvasColourBy.allCases) { option in
                    Label(option.label, systemImage: option.icon).tag(option)
                }
            }
            .pickerStyle(.inline)
        }
    }
}
