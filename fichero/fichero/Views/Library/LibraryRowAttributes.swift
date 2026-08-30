import SwiftUI

// MARK: - List-row metadata attributes (#18, Daniel 2026-08-11)

/// Which optional attributes a library LIST row displays — the Xcode-console
/// "Metadata" popover model Daniel pointed at: the row's core is title +
/// transcript, and everything else (date, type, status text, entity
/// lozenges) is opt-in per user choice.
enum LibraryRowAttribute: String, CaseIterable, Identifiable {
    /// The item's NAME — hideable in icon view (Daniel, 2026-08-23: "icon
    /// view should be able to hide icon name"). Default ON.
    case name
    case date
    case type
    case status
    case entities

    var id: String { rawValue }

    var title: String {
        switch self {
        case .name: return "Name"
        case .date: return "Date"
        case .type: return "Type"
        case .status: return "Status"
        case .entities: return "Entities"
        }
    }

    var systemImage: String {
        switch self {
        case .name: return "textformat"
        case .date: return "calendar"
        case .type: return "doc"
        case .status: return "circle.badge.checkmark"
        case .entities: return "person.text.rectangle"
        }
    }

    /// Codec for the @AppStorage backing string (comma-joined raw values).
    /// Unknown tokens are dropped so an old build's value can never trap.
    static func set(from raw: String) -> Set<LibraryRowAttribute> {
        var set = Set(raw.split(separator: ",").compactMap {
            LibraryRowAttribute(rawValue: String($0).trimmingCharacters(in: .whitespaces))
        })
        // NAME defaults ON and is stored as its ABSENCE marker ("!name"):
        // stored raws predate the attribute, and reading them as name-off
        // would hide every icon label on upgrade.
        if !raw.contains("!name") { set.insert(.name) }
        return set
    }

    static func raw(from set: Set<LibraryRowAttribute>) -> String {
        var tokens = allCases.filter { $0 != .name && set.contains($0) }.map(\.rawValue)
        if !set.contains(.name) { tokens.append("!name") }
        return tokens.joined(separator: ",")
    }

    /// The default row: entities only — the decluttered look Daniel ruled
    /// (title + transcript are always shown; they are the row, not metadata).
    static let defaultRaw = "entities"
}

/// The mini-toolbar button + popover choosing row attributes — self-contained
/// so the host (an extension, which cannot hold @State) only supplies the
/// persisted binding.
/// The SAME attribute toggles as a nestable MENU, for hosts where a popover
/// cannot live — the bottom bar's narrow-width overflow menu dropped the
/// metadata control entirely rather than embedding an inert popover row
/// (Daniel, 2026-08-29: "the bottom toolbar loses some of the filter
/// options when it's too narrow"). One binding, two coats.
struct LibraryRowAttributesMenu: View {
    @Binding var raw: String

    var body: some View {
        Menu("Metadata") {
            ForEach(LibraryRowAttribute.allCases) { attribute in
                Button {
                    var set = LibraryRowAttribute.set(from: raw)
                    if set.contains(attribute) {
                        set.remove(attribute)
                    } else {
                        set.insert(attribute)
                    }
                    raw = LibraryRowAttribute.raw(from: set)
                } label: {
                    if LibraryRowAttribute.set(from: raw).contains(attribute) {
                        Label(attribute.title, systemImage: "checkmark")
                    } else {
                        Text(attribute.title)
                    }
                }
            }
        }
    }
}

struct LibraryRowAttributesButton: View {
    @Binding var raw: String
    /// Dataset mode only: excerpt-vs-full-text lives HERE, with the other
    /// "what do rows display" choices (Daniel, 2026-08-27: "the full text
    /// excerpt is more logically part of the metadata").
    var datasetStore: DatasetModeStore?
    @State private var isPresented = false

    private func binding(for attribute: LibraryRowAttribute) -> Binding<Bool> {
        Binding(
            get: { LibraryRowAttribute.set(from: raw).contains(attribute) },
            set: { isOn in
                var set = LibraryRowAttribute.set(from: raw)
                if isOn { set.insert(attribute) } else { set.remove(attribute) }
                raw = LibraryRowAttribute.raw(from: set)
            }
        )
    }

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            Label("Metadata", systemImage: "switch.2")
                .labelStyle(.iconOnly)
        }
        .buttonStyle(.borderless)
        .help("Choose which attributes list rows display")
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Metadata")
                    .font(.headline)
                ForEach(LibraryRowAttribute.allCases) { attribute in
                    Toggle(isOn: binding(for: attribute)) {
                        Label(attribute.title, systemImage: attribute.systemImage)
                    }
                    #if os(macOS)
                    .toggleStyle(.checkbox)
                    #endif
                }
                if let datasetStore {
                    Divider()
                    Text("Text")
                        .font(.headline)
                    ForEach(DatasetModeStore.TextDetail.allCases) { choice in
                        Toggle(isOn: Binding(
                            get: { datasetStore.textDetail == choice },
                            set: { if $0 { datasetStore.textDetail = choice } }
                        )) {
                            Text(choice.rawValue)
                        }
                        #if os(macOS)
                        .toggleStyle(.checkbox)
                        #endif
                    }
                }
            }
            .padding(12)
            .frame(minWidth: 160)
        }
    }
}
