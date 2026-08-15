import SwiftUI

// MARK: - List-row metadata attributes (#18, Daniel 2026-08-11)

/// Which optional attributes a library LIST row displays — the Xcode-console
/// "Metadata" popover model Daniel pointed at: the row's core is title +
/// transcript, and everything else (date, type, status text, entity
/// lozenges) is opt-in per user choice.
enum LibraryRowAttribute: String, CaseIterable, Identifiable {
    case date
    case type
    case status
    case entities

    var id: String { rawValue }

    var title: String {
        switch self {
        case .date: return "Date"
        case .type: return "Type"
        case .status: return "Status"
        case .entities: return "Entities"
        }
    }

    var systemImage: String {
        switch self {
        case .date: return "calendar"
        case .type: return "doc"
        case .status: return "circle.badge.checkmark"
        case .entities: return "person.text.rectangle"
        }
    }

    /// Codec for the @AppStorage backing string (comma-joined raw values).
    /// Unknown tokens are dropped so an old build's value can never trap.
    static func set(from raw: String) -> Set<LibraryRowAttribute> {
        Set(raw.split(separator: ",").compactMap {
            LibraryRowAttribute(rawValue: String($0).trimmingCharacters(in: .whitespaces))
        })
    }

    static func raw(from set: Set<LibraryRowAttribute>) -> String {
        allCases.filter(set.contains).map(\.rawValue).joined(separator: ",")
    }

    /// The default row: entities only — the decluttered look Daniel ruled
    /// (title + transcript are always shown; they are the row, not metadata).
    static let defaultRaw = "entities"
}

/// The mini-toolbar button + popover choosing row attributes — self-contained
/// so the host (an extension, which cannot hold @State) only supplies the
/// persisted binding.
struct LibraryRowAttributesButton: View {
    @Binding var raw: String
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
                    .toggleStyle(.checkbox)
                }
            }
            .padding(12)
            .frame(minWidth: 160)
        }
    }
}
