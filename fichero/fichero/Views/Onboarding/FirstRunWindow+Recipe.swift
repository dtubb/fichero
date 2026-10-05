import SwiftUI

// MARK: - Recipe steps (source.onboard.*)

/// The setup screens of first run, which are also Set Up… for a project
/// (`FirstRunStep.setUpSteps`, `source.onboard.screens-in-order`). Same page chrome and navigation as the
/// other steps; the fields scroll because a recipe can be longer than the card.
extension FirstRunWindow {
    @ViewBuilder
    func recipeStepPage(_ step: FirstRunStep) -> some View {
        let store = appState.recipeSetupStore
        switch step {
        case .purpose:
            stepPage(
                title: "What are you doing?",
                subtitle: "Your purpose decides what runs by itself. Every tool stays reachable.",
                systemImage: step.icon
            ) {
                recipeCard { RecipePurposeFields(store: store) }
            }
        case .start:
            stepPage(
                title: "Start",
                subtitle: "What will run, on how many pages, and what it costs. Nothing runs before you press Start.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeStartFields(store: store) }
            }
        case .material:
            stepPage(
                title: "Your material",
                subtitle: "How your sources come in, and roughly how much there is. You can add it later.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeMaterialSourceFields(store: store, importer: importService) }
            }
        case .about:
            stepPage(
                title: "What it is",
                subtitle: "Its languages, scripts and kind. Fichero works out the rest from them.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeAboutFields(store: store) }
            }
        default:
            stepPage(
                title: "How it will be done",
                subtitle: "The steps the rules propose from your answers, and why each is there.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeProposalFields(store: store) }
            }
        }
    }

    private func recipeCard<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        ScrollView {
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(22)
        }
        .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        }
    }

    // MARK: - AI step

    /// #3121 — the two zero-cloud, on-device options with their true state.
    /// Apple Intelligence availability comes from the `/providers/apple/availability`
    /// probe (#3118) so an unavailable machine sees the concrete reason instead of
    /// discovering it at first call. MLX is always offered (Apple-silicon local
    /// runtime) with a pointer to its setup pane.
    var localFirstAIOptions: some View {
        VStack(alignment: .leading, spacing: 8) {
            appleIntelligenceOption
            localOptionRow(
                icon: "cpu",
                title: "MLX on-device models",
                detail: "Set up in Settings ▸ Local LLM.",
                detailTint: .secondary
            )
        }
        .task {
            await appState.appleAvailabilityStore.load()
        }
    }

    @ViewBuilder
    private var appleIntelligenceOption: some View {
        let status = appState.appleAvailabilityStore.status
        localOptionRow(
            icon: "apple.logo",
            title: "Apple Intelligence",
            detail: status.map { $0.available ? "Available" : $0.label } ?? "Checking availability…",
            detailTint: status?.available == false ? .orange : .secondary
        )
    }

    private func localOptionRow(icon: String, title: String, detail: String, detailTint: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .frame(width: 18)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.callout)
            LocalPrivateBadge()
            Spacer()
            Text(detail)
                .font(.caption)
                .foregroundStyle(detailTint)
                .textSelection(.enabled)
                .multilineTextAlignment(.trailing)
        }
    }
}
