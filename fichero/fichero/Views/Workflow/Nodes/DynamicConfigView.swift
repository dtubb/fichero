import SwiftUI

struct DynamicConfigView: View {
    let toolInfo: ToolInfo
    @Binding var config: [String: AnyCodableValue]?
    @Environment(DocumentStore.self) var documentStore: DocumentStore

    @State var stringValues: [String: String] = [:]
    @State var intValues: [String: Int] = [:]
    @State var doubleValues: [String: Double] = [:]
    @State var boolValues: [String: Bool] = [:]
    @State var arrayValues: [String: [String]] = [:]
    @State private var showOutputSettings = false
    @State private var showAdvancedSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(primaryKeys, id: \.self) { key in
                if let fieldSchema = getFieldSchema(for: key) {
                    configField(key: key, schema: fieldSchema)
                }
            }

            if !outputKeys.isEmpty {
                DisclosureGroup("Output Settings", isExpanded: $showOutputSettings) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(outputKeys, id: \.self) { key in
                            if let fieldSchema = getFieldSchema(for: key) {
                                configField(key: key, schema: fieldSchema)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.caption)
            }

            if !advancedKeys.isEmpty {
                DisclosureGroup("Advanced", isExpanded: $showAdvancedSettings) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(advancedKeys, id: \.self) { key in
                            if let fieldSchema = getFieldSchema(for: key) {
                                configField(key: key, schema: fieldSchema)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.caption)
            }
        }
        .onAppear {
            initializeValues()
        }
        .task {
            if isFolderTool, documentStore.collections.isEmpty {
                await documentStore.loadCollections()
            }
        }
    }

    // MARK: - Grouped Keys

    let dedicatedKeys: Set<String> = ["provider_name", "model_name", "vision_mode"]

    var visibleKeys: [String] {
        toolInfo.configSchema.keys.filter { key in
            guard !dedicatedKeys.contains(key) else { return false }
            guard let schema = getFieldSchema(for: key) else { return false }
            if isFolderTool, key == "folder_path" {
                return false
            }
            return !isHidden(schema: schema)
        }
    }

    var primaryKeys: [String] {
        if isFolderTool {
            let preferredOrder = ["folder_id", "file_types", "include_subfolders", "limit"]
            let ordered = preferredOrder.filter { visibleKeys.contains($0) }
            let rest = visibleKeys.filter { !preferredOrder.contains($0) }.sorted()
            return ordered + rest
        }

        let keys = visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            let group = getGroup(from: schema)
            return group == "primary" || group == nil
        }
        let priorityOrder = ["collection_id", "vision_mode", "max_image_dimension"]
        let priority = keys.filter { priorityOrder.contains($0) }
            .sorted { priorityOrder.firstIndex(of: $0)! < priorityOrder.firstIndex(of: $1)! }
        let prompt = keys.filter { $0 == "prompt" }
        let others = keys.filter { !priorityOrder.contains($0) && $0 != "prompt" }.sorted()
        return priority + others + prompt
    }

    var outputKeys: [String] {
        visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            return getGroup(from: schema) == "output"
        }.sorted()
    }

    var advancedKeys: [String] {
        visibleKeys.filter { key in
            guard let schema = getFieldSchema(for: key) else { return false }
            return getGroup(from: schema) == "advanced"
        }.sorted()
    }

    var isFolderTool: Bool {
        toolInfo.name == "folder"
    }
}
