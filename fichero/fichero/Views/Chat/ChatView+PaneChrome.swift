import SwiftUI

// MARK: - The chat pane's head + bottom bar (split for file_length)
//
// The 2026-08-23 chrome: [X : chat icon : lens] [conversation crumb with the
// jump-bar switcher] [+/pin], and the ONE bottom bar — new chat, model,
// grounding indicator, Save as Workspace.

extension ChatView {
    /// Explicitly typed (the reader's type-checker rule applied here).
    var chatSelector: PaneKindSelector<ChatSurfaceTab> {
        PaneKindSelector(
            kindTitle: "Chat",
            kindIcon: "bubble.left.and.bubble.right",
            lenses: ChatSurfaceTab.allCases,
            lensTitle: { (tab: ChatSurfaceTab) in tab.title },
            lensIcon: { (tab: ChatSurfaceTab) in tab.icon },
            lens: chatTabBinding
        )
    }

    /// The chat's floating head: [X : chat icon : lens] [conversation crumb —
    /// its jump-bar menu lists the other conversations] [+ / pin].
    var chatPaneHead: some View {
        PaneHead<PaneKindSelector<ChatSurfaceTab>, EmptyView, EmptyView>(
            crumbs: [PaneCrumb(
                id: currentConversation.id,
                title: currentConversation.title,
                icon: "bubble.left.and.bubble.right.fill"
            )],
            onClose: onClosePane,
            // Pin = stay on THIS conversation: switching is refused while
            // pinned (the guard in switchConversation).
            isPinned: $isConversationPinned,
            onCrumb: { crumb in
                guard !isConversationPinned,
                      let conversation = visibleConversations.first(where: { $0.id == crumb.id })
                else { return }
                switchConversation(conversation)
            },
            crumbChildren: { _ in
                visibleConversations.map { conversation in
                    PaneCrumb(
                        id: conversation.id,
                        title: conversation.title,
                        icon: "bubble.left.and.bubble.right"
                    )
                }
            },
            selector: { self.chatSelector },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }

    var chatBottomBar: some View {
        MiniToolbar {
            // New chat leads the bar (Daniel, 2026-08-23: "a plus on left,
            // the model to use, save as workspace on right" — no message
            // count, nobody cares).
            Button {
                startNewChat()
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.borderless)
            .help("New chat")
            .accessibilityLabel("New chat")
            .disabled(isConversationPinned)

            chatModelMenu

            // The grounding indicator (Daniel, 2026-08-23: "indicate context
            // is provided with current selection somehow") — the eye follows
            // the current view; the pin counts dropped-in documents.
            if let scope = attachContext.implicitScopeLabel {
                Label(scope, systemImage: "eye")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .help("Grounded on your current view: \(scope)")
            }
            if !selectedDocuments.isEmpty {
                Label("\(selectedDocuments.count)", systemImage: "pin.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .help("\(selectedDocuments.count) document(s) attached to this chat")
            }

            Spacer(minLength: 0)
            Button {
                saveAsWorkspace()
            } label: {
                Label("Save as Workspace", systemImage: "square.and.arrow.down")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            .disabled(backendConversationId == nil)
            .help(backendConversationId == nil
                  ? "Send a message first, then save this chat as a workspace"
                  : "Save this chat as a reusable workspace node")
            .accessibilityIdentifier("chatSaveAsWorkspace")
        }
    }

    /// The model choice, compact, in the bottom bar (Daniel, 2026-08-23:
    /// "the model to use" lives down here, not in a top row). The SAME
    /// picker the old toolbar used — shared, not rewritten.
    var chatModelMenu: some View {
        ChatModelPicker(
            providers: providers,
            selectedProvider: $selectedProvider,
            selectedModel: $selectedModel
        )
        .equatable()
    }
}
