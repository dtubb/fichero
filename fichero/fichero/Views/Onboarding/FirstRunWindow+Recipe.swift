import SwiftUI

// MARK: - Setup's screens (section 7b, source.onboard.*)

/// The setup screens of first run, Set Up New Project… and Set Up… (one flow,
/// `source.onboard.screens-in-order`). Same page chrome and navigation as the other steps; the
/// fields scroll because a recipe can be longer than the card. Every screen after Where it
/// lives works on the project's own store.
extension FirstRunWindow {
    @ViewBuilder
    func recipeStepPage(_ step: FirstRunStep) -> some View {
        if step == .location {
            stepPage(
                title: "Where it lives",
                subtitle: "Name the project and choose where it is kept. You can move it later.",
                systemImage: step.icon
            ) {
                recipeCard { SetupWhereItLivesFields(store: newProject) }
            }
        } else if let store {
            setupPage(step, store: store)
        } else {
            stepPage(title: step.title, subtitle: "Choose where the project lives first.", systemImage: step.icon) {
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private func setupPage(_ step: FirstRunStep, store: RecipeSetupStore) -> some View {
        switch step {
        case .purpose:
            stepPage(
                title: "What it is for",
                subtitle: "Tick everything this project is for. Each purpose is a set of jobs; tick any job on its own too.",
                systemImage: step.icon
            ) {
                recipeCard { RecipePurposeFields(store: store) }
            }
        case .material:
            stepPage(
                title: "Your material",
                subtitle: "How your sources come in, and roughly how much there is. You can add it later.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeMaterialSourceFields(
                    store: store, importer: project?.importService, syncFolders: project?.syncFolderStore
                ) }
            }
        case .keptExported:
            stepPage(
                title: "Kept exported",
                subtitle: "Keep an up-to-date copy of the work in a folder outside the project. Optional; Continue skips it.",
                systemImage: step.icon
            ) {
                recipeCard {
                    if let keptExports = project?.keptExportStore {
                        KeptExportFields(store: keptExports)
                    }
                }
            }
        case .about:
            stepPage(
                title: "What it is",
                subtitle: "Its languages, scripts, direction and kind. Fichero works out the rest from them.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeAboutFields(store: store) }
            }
        case .automatic:
            stepPage(
                title: "What runs by itself",
                subtitle: "What happens to new material after you press Start.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeAutomaticFields(store: store) }
            }
        case .start:
            stepPage(
                title: "Start",
                subtitle: "What will run, on how many pages, and what it costs. Nothing runs before you press Start.",
                systemImage: step.icon
            ) {
                recipeCard { RecipeStartFields(store: store) }
            }
        default:
            stepPage(
                title: "How it will be done",
                subtitle: "The steps the rules propose from your answers.",
                systemImage: step.icon
            ) {
                recipeCard {
                    RecipeProposalFields(store: store, onFix: { fix in handle(fix: fix, store: store) },
                                         bakeoff: project.map(BakeoffSection.Context.init(project:)))
                }
            }
        }
    }

    /// A ticked job's own screen: what the job does, in the registry's words, and its questions.
    @ViewBuilder
    func jobPage(_ job: String) -> some View {
        if let store {
            stepPage(
                title: store.title(ofJob: job),
                subtitle: store.explanation(ofJob: job)?.short ?? "",
                systemImage: "checkmark.square"
            ) {
                recipeCard { SetupJobFields(store: store, job: job) }
            }
        }
    }

    /// A step problem's fix button (`source.onboard.says-no-model`): letting pages leave this Mac
    /// is answered here and the recipe proposed again; a download, a cloud model or another model
    /// is chosen in the one catalogue, Settings › AI Models.
    private func handle(fix: String, store: RecipeSetupStore) {
        if fix == "allow-cloud" {
            Task { await store.allowCloud() }
        } else {
            appState.openSettings(tab: .aiModels)
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
                .accessibilityHidden(true)
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
