import SwiftUI

/// Configuration view for extract_entities node
struct ExtractEntitiesNodeConfig: View {
    @Binding var node: WorkflowNode

    @State private var entityTypes: Set<String> = ["people", "organizations", "locations", "dates"]
    @State private var includeContext: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Entity types
            VStack(alignment: .leading, spacing: 8) {
                Text("Entity Types")
                    .font(.caption)
                    .foregroundColor(.secondary)

                let entityTypeOptions = ["people", "organizations", "locations", "dates", "events", "products"]
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(entityTypeOptions, id: \.self) { type in
                        Toggle(type.capitalized, isOn: Binding(
                            get: { entityTypes.contains(type) },
                            set: { isOn in
                                if isOn {
                                    entityTypes.insert(type)
                                } else {
                                    entityTypes.remove(type)
                                }
                                if node.config == nil {
                                    node.config = [:]
                                }
                                node.config?["entity_types"] = .array(entityTypes.map { .string($0) })
                            }
                        ))
                        .toggleStyle(.checkbox)
                        .font(.caption)
                    }
                }
            }

            // Include context
            Toggle("Include Context", isOn: $includeContext)
                .font(.caption)
                .onChange(of: includeContext) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["include_context"] = .bool(newValue)
                }

            Text("Shows surrounding text for each entity")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .onAppear {
            loadInitialState()
        }
    }

    private func loadInitialState() {
        if let configValue = node.config?["entity_types"],
           case .array(let types) = configValue {
            entityTypes = Set(types.compactMap {
                if case .string(let type) = $0 {
                    return type
                }
                return nil
            })
        }

        if let configValue = node.config?["include_context"],
           case .bool(let context) = configValue {
            includeContext = context
        }
    }
}
