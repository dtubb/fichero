import SwiftUI

// MARK: - Action Row

struct ActionRowView: View {
    let action: ActionItem

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: action.icon)
                .font(.title2)
                .foregroundStyle(action.isBuiltin ? .blue : .orange)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(action.name)
                        .fontWeight(.medium)

                    if action.isBuiltin {
                        Text("Built-in")
                            .font(.caption2)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(.blue.opacity(0.2))
                            .cornerRadius(4)
                    }
                }

                Text(action.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                if !action.tags.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(action.tags.prefix(3), id: \.self) { tag in
                            Text(tag)
                                .font(.caption2)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(.quaternary)
                                .cornerRadius(3)
                        }
                    }
                }
            }

            Spacer()

            if action.useCount > 0 {
                VStack {
                    Text("\(action.useCount)")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text("uses")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
