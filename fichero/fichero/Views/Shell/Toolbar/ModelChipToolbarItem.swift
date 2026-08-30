import OSLog
import SwiftUI

private let logger = Logger(
    subsystem: "app.fichero.fichero",
    category: "ModelChip"
)

/// The model a run would actually use, in the toolbar beside the selection
/// (Daniel, 2026-08-28: the island says what is selected, so the default model
/// belongs to its left).
///
/// Fichero had NO visible statement of which model it was about to call. When
/// the `$vision_small` alias silently resolved to a broken provider prefix
/// (2026-08-27) there was no surface on which that could have been noticed —
/// the run simply produced worse results. This is that surface.
///
/// The chip is CONTEXTUAL, not a single global default: a page selection
/// resolves the vision tier, anything else resolves the text tier, because
/// that is the one a run on this selection would really use. Showing one fixed
/// "default model" would be a different kind of lie.
struct ModelChipToolbarItem: View {
    /// True when the current selection would be handled by a vision model.
    let prefersVision: Bool
    @Environment(AppState.self) private var appState
    /// SwiftUI's own settings action — no AppKit bridge, so this file stays
    /// inside the cross-platform rule (check_appkit_imports). macOS only:
    /// iOS marks `openSettings` explicitly unavailable (it broke the Dev
    /// Local iOS build, 2026-08-29), and the iOS chip simply omits the
    /// settings shortcut — Settings is a tab away there anyway.
    #if os(macOS)
    @Environment(\.openSettings) private var openSettings
    #endif
    /// Fetched rather than injected: nothing holds AI defaults in a shared
    /// observable today, so the chip loads its own copy and refreshes when the
    /// menu opens — which is the moment its accuracy matters.
    @State private var defaults = AIDefaults()
    /// True when the last fetch FAILED, as distinct from a genuinely unset
    /// tier — the chip must not report an engine problem as a user one.
    @State private var loadFailed = false

    /// Configured models the picker offers — vision-capable ones for a page
    /// selection, everything for text. From the same provider cache the Run
    /// Workflow menu uses, so the two lists can never disagree.
    @State private var isPresented = false
    @Environment(ChatService.self) private var chatService: ChatService?

    private var pickableModels: [(provider: String, model: String)] {
        WorkflowRunProviderCache.shared.providers.flatMap { provider in
            provider.models.compactMap { model -> (String, String)? in
                if prefersVision {
                    let visionCapable = provider.modelDetails
                        .first { $0.modelId == model }?.supportsVision
                        ?? provider.supportsVision
                    guard visionCapable else { return nil }
                }
                return (provider.id, model)
            }
        }
    }

    private var currentModel: String {
        prefersVision ? defaults.visionMediumModel : defaults.mediumModel
    }

    private var currentProvider: String {
        prefersVision ? defaults.visionMediumProvider : defaults.mediumProvider
    }

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            // A LOGO, not the model's full name (Daniel, 2026-08-29: "can't we
            // do it with a logo, rather than having all that width?"). Apple
            // has a real glyph; every other family gets a monogram in its own
            // colour — which is what makes the idea survive providers that
            // ship no logo. The full name lives one hover (help) or one click
            // (popover) away.
            ModelFamilyMark(model: currentModel, provider: currentProvider)
                .padding(.horizontal, 6)
        }
        .buttonStyle(.plain)
        .fixedSize()
        // A POPOVER that PICKS, not a menu that recites (Daniel, 2026-08-29:
        // "too much info, too much garbage — less is more, and to be able to
        // change the model there"). One list of configured models, the active
        // one ticked; choosing writes the tier this selection resolves —
        // vision for a page, text otherwise — through the same defaults the
        // run reads.
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            modelPicker
        }
        .task { await reload() }
        .help("\(prefersVision ? "Vision" : "Text") model for this selection: \(displayModel)")
        .accessibilityLabel("Model: \(displayModel)")
    }

    @ViewBuilder
    // Extracted into small CONCRETE subviews (2026-08-29): the first inline
    // version was one giant generic tuple, and the StallSampler caught its
    // opaque-type metadata instantiation stalling the main thread for 333ms
    // the first time the popover opened. Concrete row/footer types keep each
    // expression's metadata trivial.
    private var modelPicker: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if pickableModels.isEmpty {
                        Text(loadFailed
                             ? "The engine did not answer."
                             : "No models configured.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(12)
                    }
                    ForEach(pickableModels, id: \.model) { choice in
                        ModelPickerRow(
                            model: choice.model,
                            provider: choice.provider,
                            isCurrent: choice.model == currentModel
                        ) {
                            select(choice)
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
        .task {
            await WorkflowRunProviderCache.shared.ensureLoaded(chatService: chatService)
            await reload()
        }
    }

    /// Write the picked model onto the tier THIS chip resolves, so the change
    /// takes effect for exactly the runs the chip describes.
    private func select(_ choice: (provider: String, model: String)) {
        isPresented = false
        var updated = defaults
        if prefersVision {
            updated.visionMediumProvider = choice.provider
            updated.visionMediumModel = choice.model
        } else {
            updated.mediumProvider = choice.provider
            updated.mediumModel = choice.model
        }
        defaults = updated
        Task {
            do {
                try await appState.saveAIDefaults(updated)
            } catch {
                logger.error("Saving model choice failed: \(String(describing: error))")
                loadFailed = true
                await reload()
            }
        }
    }

    private func reload() async {
        // Retry until it lands. The first attempt fires at window open, which
        // routinely LOSES a race with the engine coming up — and a single
        // silent `try?` then left the chip reading "No model set" forever over
        // a perfectly configured install (Daniel, 2026-08-28). That is the same
        // shape as the Reader's poisoned cache key: a failure that cannot
        // retry itself is indistinguishable from a real absence.
        //
        // Bounded, because "not set" IS a legitimate answer and must not spin.
        for attempt in 0..<6 {
            do {
                defaults = try await appState.fetchAIDefaults()
                loadFailed = false
                return
            } catch {
                loadFailed = true
                logger.warning("AI defaults load attempt \(attempt + 1) failed: \(String(describing: error))")
                try? await Task.sleep(for: .seconds(Double(attempt + 1)))
            }
        }
    }


    /// The model the run resolves to, or an honest admission that no tier is set.
    private var displayModel: String {
        let model = prefersVision ? defaults.visionMediumModel : defaults.mediumModel
        if !model.isEmpty { return model }
        // Distinguish "the engine did not answer" from "you have not chosen".
        // Reporting the first as the second sent a user to Settings to fix
        // something that was already configured.
        return loadFailed ? "Model unavailable" : "No model set"
    }

    private var shortModel: String { Self.shorten(displayModel) }

    /// `openrouter/anthropic/claude-sonnet-5` reads as `claude-sonnet-5` — the
    /// provider path is noise in a toolbar and the tooltip carries it in full.
    /// `nonisolated`: pure string manipulation, also called from nonisolated
    /// model code (`StagedWorkflowStep.modelDescription`).
    nonisolated static func shorten(_ model: String) -> String {
        model.split(separator: "/").last.map(String.init) ?? model
    }
}


/// A model family as a compact mark: Apple's own glyph where one exists, a
/// coloured monogram everywhere else. The COLOUR carries the family (Claude
/// rust, Gemini blue, OpenAI green...), so the mark stays legible even when
/// two families share an initial.
struct ModelFamilyMark: View {
    let model: String
    let provider: String

    /// The bundled provider logos Settings already ships
    /// (Resources/Assets.xcassets/Providers/*) — matched on the MODEL first,
    /// because through OpenRouter the model's family is what the user thinks
    /// of as "the model", and the router is plumbing.
    private var logoAsset: String? {
        let haystack = "\(provider)/\(model)".lowercased()
        let table: [(needle: String, asset: String)] = [
            ("claude", "Providers/Anthropic"), ("anthropic", "Providers/Anthropic"),
            ("gemini", "Providers/GoogleAI"), ("google", "Providers/GoogleAI"),
            ("gpt", "Providers/OpenAI"), ("openai", "Providers/OpenAI"),
            ("mistral", "Providers/MistralAI"),
            ("qwen", "Providers/DashScope"),
            ("deepseek", "Providers/DeepSeek"),
            ("grok", "Providers/xAI"),
            ("groq", "Providers/Groq"),
            ("ollama", "Providers/Ollama"),
            ("lmstudio", "Providers/LMStudio"), ("lm-studio", "Providers/LMStudio"),
            ("openrouter", "Providers/OpenRouter"),
        ]
        return table.first { haystack.contains($0.needle) }?.asset
    }

    var body: some View {
        let haystack = "\(provider)/\(model)".lowercased()
        if haystack.contains("apple") {
            Image(systemName: "apple.logo")
                .font(.system(size: 12))
                .frame(width: 20, height: 20)
        } else if let logoAsset {
            Image(logoAsset)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 18, height: 18)
                .frame(width: 20, height: 20)
        } else {
            // A family with no bundled logo still gets a mark: its initial in
            // a quiet circle. This is what lets logo-first survive providers
            // that ship no logo.
            Text(model.isEmpty ? "?" : String(model.prefix(1)).uppercased())
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 20, height: 20)
                .background(.quaternary.opacity(0.5), in: Circle())
        }
    }
}


/// One configured model in the chip's picker. A concrete type on purpose —
/// see the metadata note above `modelPicker`.
private struct ModelPickerRow: View {
    let model: String
    let provider: String
    let isCurrent: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "checkmark")
                    .font(.system(size: 9, weight: .semibold))
                    .opacity(isCurrent ? 1 : 0)
                Text(ModelChipToolbarItem.shorten(model))
                    .font(.callout)
                Spacer(minLength: 12)
                Text(provider)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
