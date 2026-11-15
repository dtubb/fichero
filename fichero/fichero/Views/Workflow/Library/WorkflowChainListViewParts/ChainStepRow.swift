import SwiftUI

struct ChainStepRow: View {
    let step: ChainStep
    let index: Int
    let workflowName: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Step number
            ZStack {
                Circle()
                    .fill(.blue.opacity(0.2))
                    .frame(width: 32, height: 32)

                Text("\(index + 1)")
                    .font(.headline)
                    .foregroundStyle(.blue)
            }

            // Step details
            VStack(alignment: .leading, spacing: 4) {
                Text(step.name.isEmpty ? "Step \(index + 1)" : step.name)
                    .font(.headline)

                HStack {
                    Image(systemName: "flowchart")
                        .foregroundStyle(.secondary)
                    Text(workflowName)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if !step.inputMappings.isEmpty {
                    HStack {
                        Image(systemName: "arrow.right.circle")
                            .foregroundStyle(.tertiary)
                        Text("\(step.inputMappings.count) input mapping\(step.inputMappings.count == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }

                if step.condition != nil {
                    HStack {
                        Image(systemName: "questionmark.diamond")
                            .foregroundStyle(.orange)
                        Text("Conditional")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
            }

            Spacer()

            // Timeout indicator
            if step.timeoutSeconds != 300 {
                Text("\(step.timeoutSeconds)s")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .cornerRadius(8)
    }
}
