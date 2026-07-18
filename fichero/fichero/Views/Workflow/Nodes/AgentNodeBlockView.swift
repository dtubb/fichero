import SwiftUI

// AgentType is defined in WorkflowTypes.swift
// Using AgentType directly instead of a separate AgentNodeType

/// Block view for an agent node type in the inspector
struct AgentNodeBlockView: View {
    let agentType: AgentType
    var onTap: (() -> Void)?

    @State private var isHovering: Bool = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: agentType.icon)
                .font(.title2)
                .foregroundColor(.purple)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(agentType.displayName)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Text(agentType.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            Image(systemName: "plus.circle.fill")
                .font(.title3)
                .foregroundColor(.accentColor)
                .opacity(isHovering ? 1 : 0.5)
        }
        .padding(10)
        .background(isHovering ? Color(platformColor: .platformSelectedControl) : Color(.controlBackgroundColor))
        .cornerRadius(8)
        .onHover { hovering in
            isHovering = hovering
        }
        .onTapGesture {
            onTap?()
        }
    }
}

#Preview {
    VStack(spacing: 8) {
        ForEach(AgentType.allCases, id: \.self) { type in
            AgentNodeBlockView(agentType: type)
        }
    }
    .padding()
    .frame(width: 300)
}
