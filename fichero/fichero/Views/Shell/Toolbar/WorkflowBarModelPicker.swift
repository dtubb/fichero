import Foundation

// WHICH models a chain step may be pinned to.
//
// The bug (Daniel, 2026-09-04): "workflow not letting us see all models, just
// showing 2 — is it filtering by vision when it should use text?" It was not
// filtering by vision; it was offering the four Settings TIER defaults, which
// dedupe to two on a normal install. A user with a dozen configured models saw
// two, and the one they wanted was not among them.
//
// So the list is every configured model, from the same provider cache the Run
// Workflow menu and the toolbar chip read — the three surfaces cannot disagree
// about what exists. Nothing is ever removed for lacking a capability; a model
// that cannot serve a step is MARKED, with the reason, by
// `WorkflowBarPolicy.modelUnsuitableReason`. That ruling is from 2026-09-01
// and it applies to every model surface, not just the chip's.
extension WorkflowBarPolicy {

    /// One Settings tier and the concrete model configured for it.
    struct TierDefault: Equatable {
        let tier: String
        let provider: String
        let model: String

        init(tier: String, provider: String, model: String) {
            self.tier = tier
            self.provider = provider
            self.model = model
        }
    }

    /// Every model a step can be pinned to: the configured tiers first — they
    /// are the shortlist a user reaches for — then everything else the engine
    /// reports, alphabetically within its provider.
    ///
    /// Deduped on provider+model, never on model alone: the same model id
    /// served directly and through a router is two different calls at two
    /// different prices.
    ///
    /// `providers` empty (the cache has not answered yet) falls back to the
    /// tiers alone, so the menu is never emptier than it was before the fetch.
    static func pinnableModels(
        providers: [LLMProvider],
        tierDefaults: [TierDefault]
    ) -> [WorkflowBarModelChoice] {
        var seen = Set<String>()
        var choices: [WorkflowBarModelChoice] = []

        func visionFlag(provider: String, model: String) -> Bool? {
            guard let entry = providers.first(where: { $0.id == provider }) else {
                // Not in the cache: the catalog says NOTHING about it, which
                // is not the same as saying no.
                return nil
            }
            if let detail = entry.modelDetails.first(where: { $0.modelId == model }) {
                return detail.supportsVision
            }
            return entry.supportsVision
        }

        func append(provider: String, model: String, tier: String?) {
            let model = model.trimmingCharacters(in: .whitespaces)
            guard !model.isEmpty else { return }
            let key = "\(provider)/\(model)"
            guard !seen.contains(key) else { return }
            seen.insert(key)
            let short = ModelChipToolbarItem.shorten(model)
            // The tier is the more useful annotation when there is one — it
            // says WHY this model is at the top of the list.
            let suffix = tier ?? provider
            choices.append(WorkflowBarModelChoice(
                label: suffix.isEmpty ? short : "\(short)  ·  \(suffix)",
                provider: provider,
                model: model,
                supportsVision: visionFlag(provider: provider, model: model),
                tier: tier
            ))
        }

        for tier in tierDefaults {
            append(provider: tier.provider, model: tier.model, tier: tier.tier)
        }
        for provider in providers {
            for model in provider.models.sorted() {
                append(provider: provider.id, model: model, tier: nil)
            }
        }
        return choices
    }
}
