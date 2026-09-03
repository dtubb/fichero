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
    ///
    /// Daniel restated it on 2026-09-02, looking at a list that showed both:
    /// "the Completed pill and the date are both OFF by default, controlled
    /// from the Metadata menu." The default already said that; what did not
    /// was the STORED value on an installed build, which keeps whatever was
    /// last written and predates the ruling. Hence the `.v2` storage key on
    /// `LibraryView.rowAttributesRaw`: one reset back to the ruled default,
    /// after which the menu is the only thing that changes it.
    static let defaultRaw = "entities"

    /// The @AppStorage key. Versioned so a ruling about the DEFAULT actually
    /// reaches installs that already stored a value (2026-09-02).
    static let storageKey = "library.rowAttributes.v2"
}

// MARK: - How much snippet text a row shows (Daniel, 2026-09-02)

/// Lines of content/transcript preview a list row reserves.
///
/// "Add an option to show more lines of content per row" — the row's body text
/// was a hard-coded `lineLimit(2, reservesSpace: true)`. It stays a FIXED
/// reservation at every setting: the #4191 density cap is what keeps rows one
/// height whether or not a document has body text, so a document that loads
/// its transcript late never re-pitches the list under a scroll.
enum LibraryRowContentLines: Int, CaseIterable, Identifiable {
    case two = 2
    case four = 4
    case six = 6

    var id: Int { rawValue }

    var title: String { "\(rawValue) Lines" }

    /// The @AppStorage key and its default — two lines, the look every
    /// existing screenshot has.
    static let storageKey = "library.rowContentLines"
    static let defaultValue = LibraryRowContentLines.two

    /// Unknown/old values fall back rather than trapping, the same rule
    /// `LibraryRowAttribute.set(from:)` follows for its CSV.
    static func resolve(_ raw: Int) -> LibraryRowContentLines {
        LibraryRowContentLines(rawValue: raw) ?? defaultValue
    }
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
    /// The content-lines choice rides in the same menu — it is the same
    /// question ("what does a row show?"), asked about the body text.
    @Binding var contentLines: Int

    var body: some View {
        Menu("Metadata") {
            ForEach(LibraryRowAttribute.allCases) { attribute in
                // A `Toggle` in a macOS menu renders the SYSTEM checkmark and
                // reads its state from the binding every time the menu opens
                // (Daniel, 2026-09-02: "that menu must show checkmarks
                // reflecting current show/hide state"). The Button + inline
                // `Label(…, systemImage: "checkmark")` it replaces drew the
                // tick in the icon slot, which is not the same affordance and
                // reads as an icon rather than a state.
                Toggle(attribute.title, isOn: LibraryRowAttributes.binding(for: attribute, raw: $raw))
            }

            Divider()

            Picker("Content", selection: $contentLines) {
                ForEach(LibraryRowContentLines.allCases) { choice in
                    Text(choice.title).tag(choice.rawValue)
                }
            }
        }
    }
}

// MARK: - One binding, three coats

/// The attribute set ↔ CSV binding, shared by the popover and the menu so the
/// two coats cannot drift into different toggle semantics.
enum LibraryRowAttributes {
    static func binding(
        for attribute: LibraryRowAttribute,
        raw: Binding<String>
    ) -> Binding<Bool> {
        Binding(
            get: { LibraryRowAttribute.set(from: raw.wrappedValue).contains(attribute) },
            set: { isOn in
                var set = LibraryRowAttribute.set(from: raw.wrappedValue)
                if isOn { set.insert(attribute) } else { set.remove(attribute) }
                raw.wrappedValue = LibraryRowAttribute.raw(from: set)
            }
        )
    }
}

struct LibraryRowAttributesButton: View {
    @Binding var raw: String
    /// Lines of body text a list row reserves (Daniel, 2026-09-02). Declared
    /// BEFORE `datasetStore`: this is the memberwise initialiser, so the
    /// property order is the call-site argument order.
    @Binding var contentLines: Int
    /// Dataset mode only: excerpt-vs-full-text lives HERE, with the other
    /// "what do rows display" choices (Daniel, 2026-08-27: "the full text
    /// excerpt is more logically part of the metadata").
    var datasetStore: DatasetModeStore?
    @State private var isPresented = false

    private func binding(for attribute: LibraryRowAttribute) -> Binding<Bool> {
        LibraryRowAttributes.binding(for: attribute, raw: $raw)
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
                Divider()
                Text("Content")
                    .font(.headline)
                Picker("Content", selection: $contentLines) {
                    ForEach(LibraryRowContentLines.allCases) { choice in
                        Text(choice.title).tag(choice.rawValue)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)

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
            .frame(minWidth: 200)
        }
    }
}
