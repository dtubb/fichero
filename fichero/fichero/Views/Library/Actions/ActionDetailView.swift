import SwiftUI

// MARK: - Action Detail View

struct ActionDetailView: View {
    let action: ActionItem
    let service: ActionsService

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                HStack {
                    Image(systemName: action.icon)
                        .font(.system(size: 40))
                        .foregroundStyle(action.isBuiltin ? .blue : .orange)

                    VStack(alignment: .leading) {
                        Text(action.name)
                            .font(.title)
                            .fontWeight(.bold)

                        HStack {
                            Text(action.category.capitalized)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.blue.opacity(0.2))
                                .cornerRadius(6)

                            if action.isBuiltin {
                                Text("Built-in")
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.green.opacity(0.2))
                                    .cornerRadius(6)
                            }

                            if action.isComposite {
                                Text("Composite")
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.purple.opacity(0.2))
                                    .cornerRadius(6)
                            }
                        }
                        .font(.caption)
                    }

                    Spacer()
                }

                // Description
                if !action.description.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Description")
                            .font(.headline)
                        Text(action.description)
                            .foregroundStyle(.secondary)
                    }
                }

                // Tags
                if !action.tags.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Tags")
                            .font(.headline)
                        FlowLayout(spacing: 8) {
                            ForEach(action.tags, id: \.self) { tag in
                                Text(tag)
                                    .font(.caption)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.quaternary)
                                    .cornerRadius(6)
                            }
                        }
                    }
                }

                // Stats
                VStack(alignment: .leading, spacing: 8) {
                    Text("Statistics")
                        .font(.headline)

                    HStack(spacing: 24) {
                        StatItem(label: "Uses", value: "\(action.useCount)")
                        StatItem(label: "Author", value: action.author.isEmpty ? "Unknown" : action.author)
                    }
                }

                // Actions
                HStack(spacing: 12) {
                    Button {
                        Task {
                            await service.recordUse(actionId: action.id)
                        }
                    } label: {
                        Label("Use Action", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    if !action.isBuiltin {
                        Button(role: .destructive) {
                            Task {
                                try? await service.deleteAction(id: action.id)
                            }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
                .padding(.top)
            }
            .padding()
        }
        .navigationTitle(action.name)
    }
}

struct StatItem: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .fontWeight(.medium)
        }
    }
}
