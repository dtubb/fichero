import SwiftUI

extension DisplayAttributesStrip {
    // MARK: - Header + filter menu

    var header: some View {
        HStack(spacing: 6) {
            Text("Attributes")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            filterMenu
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 4)
    }

    var filterMenu: some View {
        Menu {
            Section("Attributes") {
                ForEach(DisplayAttribute.allCases) { attr in
                    Toggle(attr.label, isOn: binding(for: attr))
                }
            }
            Section("Scope") {
                Button {
                    includeChildren = false
                } label: {
                    HStack {
                        Text("This item only")
                        Spacer(minLength: 0)
                        if !includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                Button {
                    includeChildren = true
                } label: {
                    HStack {
                        Text("Include children")
                        Spacer(minLength: 0)
                        if includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            Section("Knowledge Graph") {
                ForEach(KGItem.allCases) { item in
                    Toggle(item.label, isOn: kgBinding(for: item))
                }
            }
            if !availableArtifactTypes.isEmpty {
                Section("Artifacts") {
                    ForEach(availableArtifactTypes, id: \.self) { type in
                        Toggle(displayName(for: type), isOn: artifactBinding(for: type))
                    }
                }
            }
            if !availableMetadataKeys.isEmpty {
                Section("Metadata") {
                    ForEach(availableMetadataKeys, id: \.self) { key in
                        Toggle(metadataLabel(for: key), isOn: metadataBinding(for: key))
                    }
                }
            }
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .font(.caption)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Choose which attributes, knowledge graph, artifacts, and metadata to show")
    }

    // MARK: - Visibility + bindings

    /// A fixed attribute renders only once the user opts it in (#4422) —
    /// matching the KG/artifact/metadata rows below, all of which were
    /// already opt-in. Default: nothing renders.
    func shouldRender(_ attr: DisplayAttribute) -> Bool {
        shownAttributes.contains(attr.rawValue)
    }

    func binding(for attr: DisplayAttribute) -> Binding<Bool> {
        Binding(
            get: { shownAttributes.contains(attr.rawValue) },
            set: { show in
                var set = shownAttributes
                if show { set.insert(attr.rawValue) } else { set.remove(attr.rawValue) }
                shownAttributesRaw = csvString(set)
            }
        )
    }

    func artifactBinding(for type: String) -> Binding<Bool> {
        Binding(
            get: { shownArtifactTypes.contains(type) },
            set: { show in
                var set = shownArtifactTypes
                if show { set.insert(type) } else { set.remove(type) }
                shownArtifactsRaw = csvString(set)
            }
        )
    }

    func kgBinding(for item: KGItem) -> Binding<Bool> {
        Binding(
            get: { shownKGItems.contains(item.rawValue) },
            set: { show in
                var set = shownKGItems
                if show { set.insert(item.rawValue) } else { set.remove(item.rawValue) }
                shownKGRaw = csvString(set)
            }
        )
    }

    func metadataBinding(for key: String) -> Binding<Bool> {
        Binding(
            get: { shownMetadataKeys.contains(key) },
            set: { show in
                var set = shownMetadataKeys
                if show { set.insert(key) } else { set.remove(key) }
                shownMetadataRaw = csvString(set)
            }
        )
    }
}
