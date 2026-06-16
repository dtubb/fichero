import SwiftUI

/// Chat surface that sits ABOVE the folder/file sidebar in the LEFT column (#2274).
///
/// Reform master plan §6d ("Chat / Agent surface") / §7.10: chat moves to the
/// LEFT/TOP. Three modes — `chat`, `results` (chat scoped to the current search
/// results / selection), and `agent` (chat that can act on the library through
/// the action registry, #1848) — plus a collapse toggle so the surface gets out
/// of the way of the file tree.
///
/// This is a thin client: it reuses the existing `ChatView`, which is wired to
/// `ChatServiceGenerated` / `ConversationServiceGenerated` via the generated
/// OpenAPI client. There is NO second networking path here — send/stream all
/// flow through the same chat service `ResearchChatPane` uses.
///
/// Mode 3 (`agent`) ships the surface and the registry-backed chat, but the
/// *autonomous* action loop (the agent deciding which registry action to invoke
/// and executing it on the UI) is EPIC #2067 and intentionally out of scope —
/// see `inlineNote` for the user-facing "coming soon" affordance.
struct SidebarChatSurface: View {
    @Binding var selectedDocuments: Set<String>

    enum Mode: String, CaseIterable, Identifiable {
        case chat
        case results
        case agent

        var id: String { rawValue }

        var label: String {
            switch self {
            case .chat: return "Chat"
            case .results: return "Results"
            case .agent: return "Agent"
            }
        }

        var systemImage: String {
            switch self {
            case .chat: return "bubble.left.and.bubble.right"
            case .results: return "text.magnifyingglass"
            case .agent: return "wand.and.stars"
            }
        }

        var caption: String {
            switch self {
            case .chat:
                return "Conversation with your library."
            case .results:
                return "Chat scoped to the current results and selection."
            case .agent:
                return "Agent can act on the library through the action registry."
            }
        }
    }

    // Per-app, restored across launches. Sidebar chat starts collapsed so the
    // file tree owns the column until the user reaches for it.
    @AppStorage("sidebarChat.expanded") private var isExpanded: Bool = false
    @AppStorage("sidebarChat.mode") private var modeRaw: String = Mode.chat.rawValue

    private var mode: Mode { Mode(rawValue: modeRaw) ?? .chat }

    private var modeBinding: Binding<Mode> {
        Binding(
            get: { Mode(rawValue: modeRaw) ?? .chat },
            set: { modeRaw = $0.rawValue }
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            header

            if isExpanded {
                Divider()
                caption
                if mode == .agent {
                    agentNote
                }
                ChatView(
                    conversation: nil,
                    selectedDocuments: $selectedDocuments,
                    onConversationUpdated: {},
                    displayMode: .list
                )
                // Keep the file tree usable: the chat body is a bounded band at
                // the top of the column, not a full-height takeover.
                .frame(minHeight: 180, maxHeight: 340)
            }

            Divider()
        }
        .background(.bar)
        .accessibilityIdentifier("sidebarChatSurface")
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.18)) { isExpanded.toggle() }
            } label: {
                Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help(isExpanded ? "Collapse chat" : "Expand chat")
            .accessibilityIdentifier("sidebarChatToggle")

            Image(systemName: "bubble.left.and.bubble.right")
                .foregroundStyle(.secondary)
            Text("Chat")
                .font(.headline)

            Spacer(minLength: 0)

            if isExpanded {
                Picker("Mode", selection: modeBinding) {
                    ForEach(Mode.allCases) { mode in
                        Image(systemName: mode.systemImage)
                            .help(mode.label)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
                .help("Switch chat mode")
                .accessibilityIdentifier("sidebarChatMode")
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    // MARK: - Captions

    private var caption: some View {
        HStack(spacing: 6) {
            Image(systemName: mode.systemImage)
            Text(mode.caption)
            Spacer(minLength: 0)
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
    }

    /// Agent-mode affordance. The registry-backed chat works today; the
    /// autonomous "agent moves the UI" loop is EPIC #2067.
    private var agentNote: some View {
        HStack(spacing: 6) {
            Image(systemName: "clock.badge")
            Text("Autonomous actions coming soon (#2067).")
            Spacer(minLength: 0)
        }
        .font(.caption2)
        .foregroundStyle(.tertiary)
        .padding(.horizontal, 10)
        .padding(.bottom, 4)
    }
}
