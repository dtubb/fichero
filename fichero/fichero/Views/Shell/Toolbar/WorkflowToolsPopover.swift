import SwiftUI

/// The individual tools, searchable — the third of Daniel's three levels
/// (tools, workflows, chains) and the one the bar could not reach.
///
/// Fichero registers ~124 tools; around 110 could stand alone as a verb. As
/// top-level toolbar items they would drown the ~13 workflow families, so they
/// live behind one entry that opens this browser: search, grouped by category,
/// each row saying what the tool does and what it consumes.
///
/// This is the node editor's palette, reachable without opening the node
/// editor — the whole complaint that started the bar.
struct WorkflowToolsPopover: View {
    let tools: [ToolInfo]
    /// Adds a tool as the next step of the chain.
    let onAdd: (ToolInfo) -> Void

    @State private var query = ""
    /// The node editor's palette hides `agent` and `mcp_*` tools behind
    /// feature flags; this popover is the same palette in a different coat,
    /// so it honours the same gate (review, 2026-08-29 — flag-off tools were
    /// stageable from here).
    @Environment(FeatureManager.self) private var featureManager

    /// Categories that describe WHERE input comes from or where it goes,
    /// rather than an operation on what is selected. Offering `files` as a
    /// verb on a selection is meaningless.
    private static let excludedCategories: Set<String> = [
        "source", "sink", "logic", "utility", "workflow"
    ]

    private var matches: [(category: String, tools: [ToolInfo])] {
        let trimmed = query.trimmingCharacters(in: .whitespaces).lowercased()
        let usable = tools.filter {
            !Self.excludedCategories.contains($0.category)
                && WorkflowPaletteGate.isBuiltinToolEnabled($0, featureManager: featureManager)
        }
        let filtered = trimmed.isEmpty ? usable : usable.filter {
            $0.displayName.lowercased().contains(trimmed)
                || $0.description.lowercased().contains(trimmed)
                || $0.name.lowercased().contains(trimmed)
        }
        return Dictionary(grouping: filtered, by: \.category)
            .map { (category: $0.key, tools: $0.value.sorted { $0.displayName < $1.displayName }) }
            .sorted { $0.category < $1.category }
    }

    /// Section headers use the palette's names, not `capitalized` on the raw
    /// key — which rendered `mcp_time` as "Mcp_time" (review, 2026-08-29).
    private static func categoryTitle(_ category: String) -> String {
        let names: [String: String] = [
            "source": "Sources", "vision": "Vision", "transform": "Transform",
            "llm": "LLM", "convert": "Convert", "logic": "Logic",
            "sink": "Outputs", "utility": "Utility", "ai": "AI",
        ]
        if let known = names[category.lowercased()] { return known }
        if category.lowercased().hasPrefix("mcp_") {
            return "MCP · " + category.dropFirst(4).capitalized
        }
        return category.capitalized
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search tools", text: $query)
                    .textFieldStyle(.plain)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)

            Divider()

            if matches.isEmpty {
                // Says WHY, rather than showing an empty box.
                Text(tools.isEmpty
                     ? "Tools have not loaded yet."
                     : "No tool matches “\(query)”.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(14)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                        ForEach(matches, id: \.category) { group in
                            Section {
                                ForEach(group.tools) { tool in
                                    toolRow(tool)
                                }
                            } header: {
                                Text(Self.categoryTitle(group.category))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 4)
                                    .background(.bar)
                            }
                        }
                    }
                }
                .frame(maxHeight: 380)
            }
        }
        .frame(width: 360)
    }

    @ViewBuilder
    private func toolRow(_ tool: ToolInfo) -> some View {
        Button {
            onAdd(tool)
        } label: {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: tool.icon.isEmpty ? "wrench.and.screwdriver" : tool.icon)
                    .font(.caption)
                    .frame(width: 16)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 5) {
                        Text(tool.displayName)
                            .font(.subheadline)
                        if tool.usesLLM {
                            // A tool that calls a model costs money; one that
                            // does not is free. That is the distinction worth
                            // making before adding a step.
                            Image(systemName: "cpu")
                                .font(.system(size: 8))
                                .foregroundStyle(.secondary)
                        }
                    }
                    if !tool.description.isEmpty {
                        Text(tool.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14)
            .padding(.top, 7)
            .padding(.bottom, expandedPrompt == tool.name ? 2 : 7)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(tool.description.isEmpty ? tool.displayName : tool.description)

        // The tool's own prompt, from the registry the store already caches —
        // no fetch, no second code path. A tool that calls a model IS its
        // prompt; a description says what it is for, the prompt says what it
        // will actually ask (Daniel, 2026-08-28).
        if tool.usesLLM {
            promptDisclosure(tool)
        }
    }

    @State private var expandedPrompt: String?

    @ViewBuilder
    private func promptDisclosure(_ tool: ToolInfo) -> some View {
        let isOpen = expandedPrompt == tool.name
        VStack(alignment: .leading, spacing: 4) {
            Button {
                expandedPrompt = isOpen ? nil : tool.name
            } label: {
                Label(isOpen ? "Hide prompt" : "Show prompt",
                      systemImage: isOpen ? "chevron.down" : "chevron.right")
                    .font(.system(size: 10))
                    .foregroundStyle(.tint)
            }
            .buttonStyle(.plain)

            if isOpen {
                // The registered prompt is the one with no config applied.
                // Say so — a Table node set to CSV sends a different one, and
                // the step's own prompt in the chain is where you see that.
                Text(tool.defaultPrompt ?? "This tool registers no prompt.")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.35),
                                in: RoundedRectangle(cornerRadius: 5))
                Text("Default prompt — a step's own settings can change it.")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.leading, 24)
        .padding(.bottom, 7)
    }
}
