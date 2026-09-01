import SwiftUI

/// The run's CONTEXT — the optional framing line every step's prompt leads
/// with, and the ellipsis menu that is now the only way to add one.
///
/// Its own file (2026-08-31) because context stopped being one token in the
/// sentence and became a small feature: a token, an editor, a removal, and a
/// menu entry, each of which has to agree with the others about whether any
/// context exists at all.
extension WorkflowBar {

    /// The trimmed framing, or nil when there is none.
    private var contextText: String? {
        guard let userContext else { return nil }
        let trimmed = userContext.wrappedValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// The run's FRAMING at the head of the sentence (Daniel, 2026-08-30):
    /// "About [this is a historical diary]," — a system-prompt line every
    /// step's prompt leads with.
    ///
    /// OPT-IN (Daniel, 2026-08-31): the token is absent until context exists,
    /// rather than sitting in every sentence as a permanent "add context…"
    /// stub. Most runs never want a framing, and a placeholder that is nearly
    /// always empty is a word the reader has to skip past every time. Entering
    /// one lives in the bar's ellipsis menu — see `chainOptionsMenu`.
    @ViewBuilder
    var contextToken: some View {
        if let userContext, let trimmed = contextText {
            Text("About")
                .font(WorkflowBar.chainConnectiveFont)
                .foregroundStyle(.secondary)
            Button {
                showsContextEditor = true
            } label: {
                // The same lozenge the subject, model and step tokens wear
                // (Daniel, 2026-09-01) — the framing is a part of the
                // sentence, so it reads as one, not as a stray blue phrase.
                Text("“\(trimmed.prefix(40))\(trimmed.count > 40 ? "…" : "")”")
                    .foregroundStyle(Color.accentColor)
                    .chainTokenLozenge(tint: Color.accentColor.opacity(0.10))
            }
            .buttonStyle(.plain)
            .help("The framing sent with every step: “\(trimmed)”. Click to edit it.")
            .accessibilityIdentifier("workflowBarContext")
            .accessibilityLabel("Run context: \(trimmed)")
            .popover(isPresented: $showsContextEditor) {
                contextEditor(userContext)
            }
            // Removal sits ON the token, the way a chain chip's ✕ does: what
            // you added in one click you take back in one click.
            Button { userContext.wrappedValue = "" } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 7))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .disabled(isRunning)
            .help("Remove the context from this run")
            .accessibilityLabel("Remove the run context")
            Text(",")
                .font(WorkflowBar.chainConnectiveFont)
                .foregroundStyle(.secondary)
                .padding(.leading, -5)
        }
    }

    /// The editor itself — one view, opened from either door (the token, or
    /// the ellipsis menu's "Add Context…").
    @ViewBuilder
    private func contextEditor(_ binding: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("What is the AI looking at?")
                .font(.headline)
            TextField(
                "e.g. A handwritten historical diary from 1926, in English.",
                text: binding, axis: .vertical
            )
            .lineLimit(2...5)
            .frame(width: 340)
            .textFieldStyle(.roundedBorder)
            .accessibilityIdentifier("workflowBarContextField")
            Text("Sent with every step of the run, before its own prompt.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(14)
    }

    /// The bar's overflow menu — where anything that is NOT part of the
    /// sentence lives. Today that is the run's framing, which stopped being a
    /// permanent token in the sentence on 2026-08-31.
    @ViewBuilder
    var chainOptionsMenu: some View {
        if let userContext {
            let existing = contextText
            Menu {
                Button(existing == nil ? "Add Context…" : "Edit Context…") {
                    showsContextEntry = true
                }
                if existing != nil {
                    Button("Remove Context") { userContext.wrappedValue = "" }
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.caption)
                    .foregroundStyle(existing == nil ? Color.secondary : Color.accentColor)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help(existing == nil
                  ? "Chain options — add a line of context telling the AI what it is looking at"
                  : "Chain options — edit or remove the run's context")
            .accessibilityLabel("Chain options")
            .accessibilityIdentifier("workflowBarOptions")
            .popover(isPresented: $showsContextEntry) {
                contextEditor(userContext)
            }
        }
    }
}
