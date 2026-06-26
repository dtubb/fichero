import SwiftUI

private struct DynamicFolderPickerOption: Identifiable {
    let folder: Document
    let depth: Int

    var id: String { folder.id }

    var indentedName: String {
        String(repeating: "  ", count: depth) + folder.name
    }
}

extension DynamicConfigView {

    // MARK: - Field Rendering

    @ViewBuilder
    // swiftlint:disable:next cyclomatic_complexity
    func configField(key: String, schema: [String: AnyCodableValue]) -> some View {
        if let type = getType(from: schema) {
            let description = getDescription(from: schema)
            let label = key.replacingOccurrences(of: "_", with: " ").capitalized

            VStack(alignment: .leading, spacing: 4) {
                if type != "boolean" {
                    Text(label)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                switch type {
                case "string":
                    if isFolderTool, key == "folder_id" {
                        folderPickerField()
                    } else if let enumValues = getEnum(from: schema) {
                        enumPicker(key: key, label: label, options: enumValues, description: description)
                    } else if key == "prompt" {
                        promptEditor(key: key, description: description)
                    } else {
                        stringField(key: key, description: description)
                    }

                case "integer":
                    integerField(key: key, schema: schema, description: description)

                case "number":
                    numberSlider(key: key, schema: schema, description: description)

                case "array":
                    arrayField(key: key, schema: schema, description: description)

                case "boolean":
                    booleanToggle(key: key, description: description, label: label)

                default:
                    Text("Unsupported type: \(type)")
                        .font(.caption)
                        .foregroundColor(.red)
                }

                if type != "boolean", let desc = description {
                    Text(desc)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Field Types

    func stringField(key: String, description: String?) -> some View {
        TextField(description ?? "Enter value", text: Binding(
            get: { stringValues[key] ?? "" },
            set: { newValue in
                stringValues[key] = newValue
                updateConfig(key: key, value: .string(newValue))
            }
        ))
        .textFieldStyle(.roundedBorder)
    }

    func enumPicker(key: String, label: String, options: [String], description: String?) -> some View {
        Picker(label, selection: Binding(
            get: { stringValues[key] ?? options.first ?? "" },
            set: { newValue in
                stringValues[key] = newValue
                updateConfig(key: key, value: .string(newValue))
            }
        )) {
            ForEach(options, id: \.self) { option in
                Text(option).tag(option)
            }
        }
        .pickerStyle(.menu)
    }

    func promptEditor(key: String, description: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ZStack(alignment: .topLeading) {
                if stringValues[key]?.isEmpty ?? true, let defaultPrompt = toolInfo.defaultPrompt {
                    Text(defaultPrompt)
                        .font(.caption)
                        .foregroundColor(.secondary.opacity(0.7))
                        .padding(.horizontal, 4)
                        .padding(.vertical, 8)
                }

                MacPlainTextEditor(text: Binding(
                    get: { stringValues[key] ?? "" },
                    set: { newValue in
                        stringValues[key] = newValue
                        if newValue.isEmpty {
                            removeConfig(key: key)
                        } else {
                            updateConfig(key: key, value: .string(newValue))
                        }
                    }
                ), font: .preferredFont(forTextStyle: .caption1))
            }
            .frame(minHeight: 80)
            .background(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color(.separatorColor), lineWidth: 1)
            )

            if !(stringValues[key]?.isEmpty ?? true) {
                Button {
                    stringValues[key] = ""
                    removeConfig(key: key)
                } label: {
                    Label("Reset to default", systemImage: "arrow.counterclockwise")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }
        }
    }

    func integerField(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        Group {
            if key == "max_image_dimension" {
                Picker("Max Image Size", selection: Binding(
                    get: { intValues[key] ?? 11024 },
                    set: { newValue in
                        intValues[key] = newValue
                        updateConfig(key: key, value: .int(newValue))
                    }
                )) {
                    Text("512px (Fastest)").tag(512)
                    Text("768px (Fast)").tag(768)
                    Text("1024px (Balanced)").tag(1024)
                    Text("1536px (Detailed)").tag(1536)
                    Text("2048px").tag(2048)
                    Text("11024px (Default)").tag(11024)
                    Text("Original Size (Maximum)").tag(0)
                }
                .pickerStyle(.menu)
            } else {
                TextField("Enter number", value: Binding(
                    get: { intValues[key] ?? 0 },
                    set: { newValue in
                        intValues[key] = newValue
                        updateConfig(key: key, value: .int(newValue))
                    }
                ), formatter: NumberFormatter())
                .textFieldStyle(.roundedBorder)
            }
        }
    }

    func booleanToggle(key: String, description: String?, label: String) -> some View {
        Toggle(description ?? label, isOn: Binding(
            get: { boolValues[key] ?? false },
            set: { newValue in
                boolValues[key] = newValue
                updateConfig(key: key, value: .bool(newValue))
            }
        ))
    }

    func numberSlider(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        let minVal = getMin(from: schema) ?? 0
        let maxVal = getMax(from: schema) ?? 1
        let step = maxVal <= 2 ? 0.1 : 1.0

        return HStack(spacing: 8) {
            Slider(
                value: Binding(
                    get: { doubleValues[key] ?? getDefaultDouble(from: schema) },
                    set: { newValue in
                        doubleValues[key] = newValue
                        updateConfig(key: key, value: .double(newValue))
                    }
                ),
                in: minVal...maxVal,
                step: step
            )
            Text(String(format: step < 1 ? "%.1f" : "%.0f", doubleValues[key] ?? getDefaultDouble(from: schema)))
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 30, alignment: .trailing)
        }
    }

    func getDefaultDouble(from schema: [String: AnyCodableValue]) -> Double {
        switch schema["default"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return 0
        }
    }

    func arrayField(key: String, schema: [String: AnyCodableValue], description: String?) -> some View {
        let joined = (arrayValues[key] ?? getDefaultArray(from: schema)).joined(separator: "; ")

        return TextField(description ?? "Values (semicolon-separated)", text: Binding(
            get: { stringValues["\(key)_edit"] ?? joined },
            set: { newValue in
                stringValues["\(key)_edit"] = newValue
                let items = newValue
                    .split(separator: ";")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                arrayValues[key] = items
                let arrayValue = AnyCodableValue.array(items.map { .string($0) })
                updateConfig(key: key, value: arrayValue)
            }
        ))
        .textFieldStyle(.roundedBorder)
        .font(.caption)
    }

    func getDefaultArray(from schema: [String: AnyCodableValue]) -> [String] {
        if case .array(let values) = schema["default"] {
            return values.compactMap {
                if case .string(let str) = $0 { return str }
                return nil
            }
        }
        return []
    }

    @ViewBuilder
    private func folderPickerField() -> some View {
        let folderOptions = buildFolderOptions(from: documentStore.collections)

        Picker("Folder", selection: Binding(
            get: { stringValues["folder_id"] ?? "" },
            set: { newValue in
                stringValues["folder_id"] = newValue
                updateConfig(key: "folder_id", value: .string(newValue))

                if let folder = folderOptions.first(where: { $0.folder.id == newValue })?.folder {
                    let resolvedPath = folder.path ?? "/"
                    stringValues["folder_path"] = resolvedPath
                    updateConfig(key: "folder_path", value: .string(resolvedPath))
                }
            }
        )) {
            Text("Select folder...").tag("")
            ForEach(folderOptions) { option in
                Text(option.indentedName).tag(option.folder.id)
            }
        }
        .pickerStyle(.menu)

        if folderOptions.isEmpty {
            Text("No folders found. Create one in Library first.")
                .font(.caption)
                .foregroundColor(.secondary)
                .italic()
        }
    }

    private func buildFolderOptions(from documents: [Document]) -> [DynamicFolderPickerOption] {
        let allFolders = documents
            .filter { $0.docType == .folder }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }

        let validFolderIds = Set(allFolders.map(\.id))

        var childrenMap: [String: [Document]] = [:]
        for folder in allFolders {
            guard let parentId = folder.parentId, validFolderIds.contains(parentId) else { continue }
            childrenMap[parentId, default: []].append(folder)
        }

        for key in childrenMap.keys {
            childrenMap[key]?.sort { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        }

        let inboxRoots = allFolders.filter { $0.parentId == nil && $0.name == "Inbox" }
        let otherRoots = allFolders
            .filter { folder in
                folder.parentId == nil && folder.name != "Inbox"
            }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        let orderedRoots = inboxRoots + otherRoots

        var options: [DynamicFolderPickerOption] = []

        func traverse(_ folder: Document, depth: Int) {
            options.append(DynamicFolderPickerOption(folder: folder, depth: depth))
            for child in childrenMap[folder.id] ?? [] {
                traverse(child, depth: depth + 1)
            }
        }

        for root in orderedRoots {
            traverse(root, depth: 0)
        }

        return options
    }
}
