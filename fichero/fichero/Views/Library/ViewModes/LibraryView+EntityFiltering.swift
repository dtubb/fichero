import SwiftUI

// MARK: - Entity Filtering

extension LibraryView {
    /// EntityType raw values currently hidden (KG canonical vocabulary).
    /// Translated to the lozenge-row scope names via `kgKindToLozenge`.
    private var hiddenKgKinds: Set<String> {
        Set(hiddenKindsCSV.split(separator: ",").map(String.init).filter { !$0.isEmpty })
    }

    /// Map KG EntityType raw values to the lozenge-scope tokens used by
    /// MailStyleRow / ArtifactEntitiesView (#882). Dates have no KG
    /// counterpart and stay on a Library-only toggle.
    struct KgKindMapping {
        let kind: String
        let scope: String
        let label: String
    }
    private static let kgKindToLozenge: [KgKindMapping] = [
        KgKindMapping(kind: "person", scope: "people", label: "People"),
        KgKindMapping(kind: "location", scope: "places", label: "Places"),
        KgKindMapping(kind: "organization", scope: "organizations", label: "Organizations"),
        KgKindMapping(kind: "event", scope: "events", label: "Events"),
        KgKindMapping(kind: "concept", scope: "keywords", label: "Keywords")
    ]

    /// Set of entity-type ids the user wants visible in list rows.
    /// Drives `MailStyleRow` → `ArtifactEntitiesView` filtering. (#519
    /// follow-up; #887 now derives from shared @AppStorage.)
    var listVisibleEntityTypes: Set<String> {
        var set = Set<String>()
        let hidden = hiddenKgKinds
        for entry in Self.kgKindToLozenge where !hidden.contains(entry.kind) {
            set.insert(entry.scope)
        }
        if showDatesEntities { set.insert("dates") }
        return set
    }

    /// Per-kind binding into the shared `inspector.kg.hiddenKinds` CSV.
    /// Mirrors what `OntologyBrowser` does so toggling a kind here also
    /// toggles it in the KG browser + document-inspector KG tab. (#887)
    private func bindingFor(kind: String) -> Binding<Bool> {
        Binding(
            get: { !hiddenKgKinds.contains(kind) },
            set: { isOn in
                var set = hiddenKgKinds
                if isOn {
                    set.remove(kind)
                } else {
                    set.insert(kind)
                }
                hiddenKindsCSV = set.sorted().joined(separator: ",")
            }
        )
    }

    /// Top-right filter menu — toggles per-entity-type visibility.
    /// Lives as a `ToolbarItem` so it shows in icon / list / table / map.
    /// People / Places / Organizations / Events / Keywords share state
    /// with OntologyBrowser via @AppStorage; Dates stays Library-only.
    /// (#883, #887)
    @ViewBuilder
    var entityFilterMenu: some View {
        Menu {
            ForEach(Self.kgKindToLozenge, id: \.kind) { entry in
                Toggle(entry.label, isOn: bindingFor(kind: entry.kind))
            }
            Toggle("Dates", isOn: $showDatesEntities)
            Divider()
            Button("Show All") {
                hiddenKindsCSV = ""
                showDatesEntities = true
            }
            Button("Hide All") {
                hiddenKindsCSV = Self.kgKindToLozenge.map(\.kind).sorted().joined(separator: ",")
                showDatesEntities = false
            }
        } label: {
            Label("Filter Entities", systemImage: "line.3.horizontal.decrease.circle")
        }
        .help("Filter entity types shown")
    }
}
