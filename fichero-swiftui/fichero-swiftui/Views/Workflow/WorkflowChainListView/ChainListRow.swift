import SwiftUI

struct ChainListRow: View {
    let chain: WorkflowChain
    let isExecuting: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(chain.name)
                        .font(.headline)

                    if isExecuting {
                        ProgressView()
                            .controlSize(.small)
                    }
                }

                if !chain.description.isEmpty {
                    Text(chain.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Text("\(chain.steps.count) step\(chain.steps.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Spacer()

            Image(systemName: "link")
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
