import SwiftUI

/// A lightweight, backend-compatible UI foundation for stage/variant browsing
/// in the document inspector (#1174). Reads optional metadata keys and renders
/// stage navigation plus variant/recipe controls without destructive writes.
struct StageVariantInspector: View {
    let document: Document

    @State private var selectedStage: PaleographyStage = .a
    @State private var selectedVariantId: String?
    @State private var stackEnabled: Set<String> = []

    private var state: StageVariantState {
        StageVariantState.from(document: document)
    }

    private var variantsForStage: [StageVariant] {
        state.stages[selectedStage] ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Stage Variants")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 8)
                Picker("Stage", selection: $selectedStage) {
                    ForEach(PaleographyStage.allCases) { stage in
                        Text(stage.displayName).tag(stage)
                    }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 220)
            }

            if variantsForStage.isEmpty {
                Text("No variants for this stage yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(variantsForStage) { variant in
                            Button {
                                selectedVariantId = variant.id
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: variant.isCanonical ? "checkmark.seal.fill" : "seal")
                                        .foregroundStyle(variant.isCanonical ? Color.accentColor : Color.secondary)
                                    Text(variant.name)
                                        .foregroundStyle(.primary)
                                    Spacer(minLength: 0)
                                    if let count = variant.operationCount {
                                        Text("\(count) ops")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.horizontal, 8)
                                .padding(.vertical, 6)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(selectedVariantId == variant.id ? Color.accentColor.opacity(0.12) : Color.clear)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxHeight: 120)
            }

            if let selected = selectedVariant {
                Divider()
                Text("Operation Stack")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if selected.operations.isEmpty {
                    Text("No operations recorded for this variant")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(selected.operations, id: \.id) { operation in
                            Toggle(isOn: Binding(
                                get: { stackEnabled.contains(operation.id) },
                                set: { enabled in
                                    if enabled {
                                        stackEnabled.insert(operation.id)
                                    } else {
                                        stackEnabled.remove(operation.id)
                                    }
                                }
                            )) {
                                Text(operation.label)
                                    .font(.caption)
                            }
                            .toggleStyle(.checkbox)
                        }
                    }
                }

                HStack(spacing: 8) {
                    Button("Promote Canonical") {}
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    Button("Compare A/B") {}
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    Spacer(minLength: 0)
                }
                .disabled(true) // backend recipe/provenance mutation endpoints are not wired yet
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.18))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .onAppear {
            if selectedVariantId == nil {
                selectedVariantId = variantsForStage.first?.id
            }
            if stackEnabled.isEmpty, let ops = selectedVariant?.operations {
                stackEnabled = Set(ops.map(\.id))
            }
        }
        .onChange(of: selectedStage) { _, _ in
            selectedVariantId = variantsForStage.first?.id
            stackEnabled = Set(selectedVariant?.operations.map(\.id) ?? [])
        }
    }

    private var selectedVariant: StageVariant? {
        guard let selectedVariantId else { return variantsForStage.first }
        return variantsForStage.first(where: { $0.id == selectedVariantId })
    }
}

enum PaleographyStage: String, CaseIterable, Identifiable {
    case stageA = "a"
    case stageB = "b"
    case stageC = "c"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .stageA: return "A"
        case .stageB: return "B"
        case .stageC: return "C"
        }
    }
}

struct StageOperation: Equatable {
    let id: String
    let label: String
}

struct StageVariant: Identifiable, Equatable {
    let id: String
    let name: String
    let isCanonical: Bool
    let operationCount: Int?
    let operations: [StageOperation]
}

struct StageVariantState: Equatable {
    let stages: [PaleographyStage: [StageVariant]]

    static func from(document: Document) -> StageVariantState {
        // Expected metadata shape (best-effort, optional):
        // stage_variants: {
        //   "a": [{"id":"raw","name":"Raw","canonical":true,"operations":[...]}, ...],
        //   "b": [...],
        //   "c": [...]
        // }
        guard let root = document.metadata["stage_variants"]?.value as? [String: Any] else {
            return StageVariantState(stages: [:])
        }

        var mapped: [PaleographyStage: [StageVariant]] = [:]
        for stage in PaleographyStage.allCases {
            guard let rows = root[stage.rawValue] as? [[String: Any]] else { continue }
            mapped[stage] = rows.compactMap(parseVariant)
        }
        return StageVariantState(stages: mapped)
    }

    private static func parseVariant(_ row: [String: Any]) -> StageVariant? {
        let id = (row["id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = (row["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let id, !id.isEmpty, let name, !name.isEmpty else { return nil }

        let canonical = row["canonical"] as? Bool ?? false
        let opsRows = row["operations"] as? [[String: Any]] ?? []
        let ops = opsRows.enumerated().compactMap { idx, operation -> StageOperation? in
            if let label = (operation["label"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty {
                return StageOperation(id: "\(id)-\(idx)", label: label)
            }
            if let name = (operation["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty {
                return StageOperation(id: "\(id)-\(idx)", label: name)
            }
            return nil
        }

        return StageVariant(
            id: id,
            name: name,
            isCanonical: canonical,
            operationCount: row["operation_count"] as? Int ?? (!ops.isEmpty ? ops.count : nil),
            operations: ops
        )
    }
}
