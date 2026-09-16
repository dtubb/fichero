import SwiftUI

/// Toolbar for Chat view with model selection and chat controls.
///
/// Xcode-chat layout (#2449): a New-conversation icon on the leading edge, the
/// conversation title as a center menu that jumps to earlier conversations (it
/// doubles as the history affordance), and the model picker + a compact scope
/// chip trailing. The always-on "All documents" label is dropped — the default
/// scope is implied, and the header stays clean ("the old one was too much").
struct ChatViewToolbar: View {
    // Conversation header
    let conversationTitle: String
    let conversations: [Conversation]
    let onSelectConversation: (Conversation) -> Void

    // Document scope (#2449 hybrid): the implicit current-view label (what the
    // chat is grounded on by default) + the count of PINNED documents layered on
    // top via the paperclip.
    let implicitScopeLabel: String?
    let selectedDocumentsCount: Int
    let onClearDocuments: () -> Void

    // Model selection
    let providers: [LLMProvider]
    @Binding var selectedProvider: String
    @Binding var selectedModel: String

    // Actions
    let onNewChat: () -> Void

    var body: some View {
        // Rebuilt on MiniToolbar (#3038) — standard height + glass chrome, one
        // shared toolbar language.
        MiniToolbar(content: {
            // Leading: New conversation (Xcode top-left).
            Button(action: onNewChat) {
                Image(systemName: "square.and.pencil")
            }
            .buttonStyle(.plain)
            .help("New conversation")
            .accessibilityLabel("New conversation")

            Spacer(minLength: 8)

            // Center: the conversation title IS a menu that jumps to earlier
            // conversations (#2449) — also the history affordance.
            ChatConversationMenu(
                conversationTitle: conversationTitle,
                conversations: conversations,
                onSelectConversation: onSelectConversation
            )
            .equatable()

            Spacer(minLength: 8)

            // Trailing: the active grounding — implicit current-view scope +
            // pinned documents (#2449 hybrid) — then the model picker.
            if implicitScopeLabel != nil || selectedDocumentsCount > 0 {
                scopeIndicator
            }
            ChatModelPicker(
                providers: providers,
                selectedProvider: $selectedProvider,
                selectedModel: $selectedModel
            )
            .equatable()
        })
    }

    /// The active chat grounding (#2449 hybrid): the implicit current-view scope
    /// (an eye — follows what you're looking at) plus the pinned documents (a
    /// pin — kept as you navigate), so the user can always see what the chat is
    /// grounded on.
    @ViewBuilder
    private var scopeIndicator: some View {
        HStack(spacing: 8) {
            if let implicitScopeLabel {
                Label(implicitScopeLabel, systemImage: "eye")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .help("Grounded on your current view: \(implicitScopeLabel)")
            }
            if selectedDocumentsCount > 0 {
                HStack(spacing: 4) {
                    Label("\(selectedDocumentsCount)", systemImage: "pin.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Button("Clear", action: onClearDocuments)
                        .font(.caption)
                        .buttonStyle(.plain)
                        .foregroundColor(.accentColor)
                }
                .help("\(selectedDocumentsCount) pinned document(s) — kept in scope as you navigate")
            }
        }
    }
}

// MARK: - Equatable menu subtrees (#23)

// Both menus are AppKit-backed popups (NSPopUpButton); re-syncing an NSMenu
// costs real main-thread time. Every PAGE FLIP changes only the toolbar's
// implicit scope label, but that re-evaluated the whole toolbar body and
// re-synced both menus — a 738ms NSPopUpButtonCell stall per flip
// (2026-08-12). Each menu is its own Equatable view so SwiftUI skips its
// body unless the data it actually renders changed. `.equatable()` is
// load-bearing: the @Binding/closure fields defeat SwiftUI's reflective
// comparison, so without it the views compare unequal every time.

private struct ChatConversationMenu: View, Equatable {
    let conversationTitle: String
    let conversations: [Conversation]
    let onSelectConversation: (Conversation) -> Void

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.conversationTitle == rhs.conversationTitle
            && lhs.conversations.map(\.id) == rhs.conversations.map(\.id)
            && lhs.conversations.map(\.title) == rhs.conversations.map(\.title)
    }

    var body: some View {
        Menu {
            if conversations.isEmpty {
                Text("No earlier conversations")
            } else {
                Section("Earlier Conversations") {
                    ForEach(conversations) { conv in
                        Button {
                            onSelectConversation(conv)
                        } label: {
                            Text(conv.title.isEmpty ? "Untitled" : conv.title)
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(conversationTitle.isEmpty ? "New Chat" : conversationTitle)
                    .font(.headline)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Switch conversation")
        .accessibilityLabel("Conversation history")
    }
}

struct ChatModelPicker: View, Equatable {
    let providers: [LLMProvider]
    @Binding var selectedProvider: String
    @Binding var selectedModel: String

    /// Popover open state. Not part of the value's identity, so it stays out of
    /// the Equatable comparison below — SwiftUI still skips the body unless the
    /// selection or provider list changed (the perf note above the struct).
    @State private var isPresented = false
    #if os(macOS)
    // SwiftUI's own settings action — no AppKit bridge, so this file stays
    // inside the cross-platform rule (check_appkit_imports). The "AI Settings…"
    // footer matches the island's picker (ModelChipToolbarItem.modelPicker).
    @Environment(\.openSettings) private var openSettings
    #endif

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        // Equatable's requirement is nonisolated, but the compared properties
        // are main-actor (View members). SwiftUI diffs on the main actor, so
        // assume it rather than weakening the properties' isolation.
        MainActor.assumeIsolated {
            lhs.selectedProvider == rhs.selectedProvider
                && lhs.selectedModel == rhs.selectedModel
                && lhs.providers == rhs.providers
        }
    }

    /// The pickable list, from the ONE shared builder every model surface reads
    /// (spec RATIFIED 2026-09-15), so chat cannot drift its own list or labels.
    /// The chat toolbar has no Settings-tier defaults on hand (they are not
    /// passed in), so `tierDefaults` is empty — the builder then returns every
    /// configured model, provider-grouped and alphabetical, which is exactly
    /// what chat offered before, only now via the shared code path.
    private var choices: [SharedModelChoice] {
        SharedModelListBuilder.build(providers: providers, tierDefaults: [])
    }

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            // Icon only (Daniel, 2026-08-23: the bar "doesn't need to say
            // what the model is") — the choice lives in the popover and the
            // hover help.
            Image(systemName: "cpu")
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(.controlBackgroundColor))
                .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .disabled(providers.isEmpty)
        // A POPOVER that PICKS, rendering the SHARED row — the same face the
        // island, Settings and the comparison sheet show — not a bespoke Menu.
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            picker
        }
    }

    @ViewBuilder
    private var picker: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if choices.isEmpty {
                        VStack(spacing: 8) {
                            Text("No models available. Add a provider in AI Settings.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 12)
                        }
                        .frame(maxWidth: .infinity, minHeight: 180)
                    }
                    ForEach(choices) { choice in
                        SharedModelRow(
                            choice: choice,
                            isCurrent: choice.provider == selectedProvider
                                && choice.model == selectedModel
                        ) {
                            // Provider first, then model — the same write order
                            // the old Menu used.
                            selectedProvider = choice.provider
                            selectedModel = choice.model
                            isPresented = false
                        }
                    }
                }
                .padding(.vertical, 6)
            }
            .frame(maxHeight: 320)
            #if os(macOS)
            Divider()
            Button("AI Settings…") {
                isPresented = false
                openSettings()
            }
            .buttonStyle(.plain)
            .font(.caption)
            .foregroundStyle(.tint)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            #endif
        }
        .frame(minWidth: 230)
    }
}
