import SwiftUI

/// Renders one `ToolCall` inside the conversation stream — the visible form of
/// "the model did an audited thing" (see
/// `docs/design/agentic-surface-consolidation-fabel-review.md`, §3).
///
/// Instrument, not interlocutor: it states the action, its status, who acted,
/// and its provenance (audited badge / unaudited-mutation flag). It never
/// narrates in the first person. Compact by default; params expand on demand so
/// a run of calls stays scannable ("Every Frame Perfect").
struct ToolCallCard: View {
    let toolCall: ToolCall

    @State private var showParams = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: toolCall.statusIcon)
                    .font(.caption)
                    .foregroundStyle(statusColor)
                    .symbolEffect(.pulse, isActive: toolCall.status == .running)

                Text(toolCall.actionName)
                    .font(.caption.monospaced())
                    .foregroundStyle(.primary)

                provenanceBadge

                Spacer(minLength: 0)

                if !toolCall.paramsSummary.isEmpty {
                    Button {
                        showParams.toggle()
                    } label: {
                        Image(systemName: showParams ? "chevron.down" : "chevron.right")
                            .font(.caption2)
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(showParams ? "Hide parameters" : "Show parameters")
                }
            }

            if showParams, !toolCall.paramsSummary.isEmpty {
                Text(toolCall.paramsSummary)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .padding(.leading, 20)
            }

            Text(toolCall.actor)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.leading, 20)
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .cornerRadius(8)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("toolCallCard")
    }

    private var statusColor: Color {
        switch toolCall.status {
        case .pending: return .secondary
        case .running: return .accentColor
        case .ok: return .green
        case .error: return .red
        }
    }

    /// Provenance in plain language: a recorded action is in the app's history
    /// (attributable + undoable via the one audited action layer, #1848); a
    /// write with no record slipped past it and is surfaced loudly, matching
    /// prefer-raise-over-silent. ("audited" is engine jargon — the user sees
    /// "recorded".)
    @ViewBuilder
    private var provenanceBadge: some View {
        if toolCall.isAudited {
            Label("recorded", systemImage: "clock.arrow.circlepath")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .labelStyle(.titleAndIcon)
                .help("Recorded in history — who did it, and undoable (\(toolCall.auditId ?? ""))")
        } else if toolCall.isUnrecordedMutation {
            // Only a KNOWN write with no record — never a read (no crying wolf).
            Label("not recorded", systemImage: "exclamationmark.shield")
                .font(.caption2)
                .foregroundStyle(.orange)
                .labelStyle(.titleAndIcon)
                .help("This change left no history entry — it isn't attributable or undoable")
        }
    }
}

#Preview {
    VStack(spacing: 8) {
        ToolCallCard(toolCall: ToolCall(
            actionName: "document.move",
            params: ["node_id": AnyCodable(42), "target": AnyCodable("/Inbox")],
            actor: "Claude (model-user)",
            auditId: "audit-123",
            status: .ok
        ))
        ToolCallCard(toolCall: ToolCall(
            actionName: "web.download",
            params: ["url": AnyCodable("https://example.org/map.jpg")],
            actor: "Claude (model-user)",
            status: .error
        ))
    }
    .padding()
    .frame(width: 420)
}
