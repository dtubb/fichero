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
    ///
    /// The list itself is now the SHARED builder's — `SharedModelListBuilder`
    /// IS this function's own tier-first/provider-grouped/provider+model-deduped
    /// logic, lifted out verbatim so every model surface reads one list (spec
    /// RATIFIED 2026-09-15). This wrapper only re-dresses each shared choice in
    /// the workflow bar's `WorkflowBarModelChoice`, whose `label` the bar's
    /// menu, tier-suffix matching and pin persistence still read.
    /// - Parameter roleDefaults: the role-default alias rows (#4883,
    ///   `models.role-defaults-always-offered`) — built once by the caller
    ///   via `SharedModelListBuilder.roleDefaultAliases`, the SAME rows the
    ///   node popover offers, so the bar can choose "$small"/"$large"/etc,
    ///   not only a named model.
    static func pinnableModels(
        providers: [LLMProvider],
        tierDefaults: [TierDefault],
        roleDefaults: [SharedModelChoice] = []
    ) -> [WorkflowBarModelChoice] {
        let shared = SharedModelListBuilder.build(
            providers: providers,
            tierDefaults: tierDefaults.map {
                SharedModelListBuilder.TierDefault(
                    tier: $0.tier, provider: $0.provider, model: $0.model)
            },
            roleDefaults: roleDefaults
        )
        return shared.map { choice in
            // A role-default row's `displayName` already carries its own
            // "$small — resolved model" annotation — appending a suffix
            // would repeat it. Only a concrete model gets the
            // `"<short>  ·  <suffix>"` label the bar has always shown.
            if isModelAliasProviderId(choice.provider) {
                return WorkflowBarModelChoice(
                    label: choice.displayName,
                    provider: choice.provider,
                    model: choice.model,
                    supportsVision: choice.supportsVision,
                    tier: choice.tier
                )
            }
            // The tier is the more useful annotation when there is one — it
            // says WHY this model is at the top of the list; otherwise the
            // provider names it. Same `"<short>  ·  <suffix>"` label the bar
            // has always shown.
            let suffix = choice.tier ?? choice.provider
            return WorkflowBarModelChoice(
                label: suffix.isEmpty
                    ? choice.displayName
                    : "\(choice.displayName)  ·  \(suffix)",
                provider: choice.provider,
                model: choice.model,
                supportsVision: choice.supportsVision,
                tier: choice.tier
            )
        }
    }
}
