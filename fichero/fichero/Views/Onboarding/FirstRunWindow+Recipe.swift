import SwiftUI

// MARK: - Setup's four steps (section 7b, ruled 2026-10-06, #5492; source.onboard.*)

/// The four setup steps of first run, Set Up New Project… and Set Up… (one flow,
/// `source.onboard.screens-in-order`). Same page chrome and navigation as the other steps; the
/// fields scroll because a step can be longer than the card. Every step after Your project
/// works on the project's own store. One sentence per step; no disclosure (#5481).
extension FirstRunWindow {
    @ViewBuilder
    func recipeStepPage(_ step: FirstRunStep) -> some View {
        if step == .project {
            stepPage(
                title: "Your project",
                subtitle: "Name it and say where it lives; most projects live inside Fichero.",
                systemImage: step.icon
            ) {
                recipeCard { SetupWhereItLivesFields(store: newProject) }
            }
        } else if let store {
            setupPage(step, store: store)
        } else {
            stepPage(title: step.title, subtitle: "Make the project first.", systemImage: step.icon) {
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private func setupPage(_ step: FirstRunStep, store: RecipeSetupStore) -> some View {
        switch step {
        case .material:
            stepPage(
                title: "Your material",
                subtitle: "How your sources come in and what they are; Fichero works out the rest.",
                systemImage: step.icon
            ) {
                recipeCard {
                    VStack(alignment: .leading, spacing: 16) {
                        RecipeMaterialSourceFields(
                            store: store, importer: project?.importService, syncFolders: project?.syncFolderStore
                        )
                        Divider()
                        RecipeAboutFields(store: store)
                    }
                }
            }
        case .purpose:
            stepPage(
                title: "What you want to do",
                subtitle: "Tick everything this project is for; each one asks only what it needs.",
                systemImage: step.icon
            ) {
                recipeCard { RecipePurposeFields(store: store) }
            }
        default:
            stepPage(
                title: "Ready",
                subtitle: "The plan from your answers; nothing runs before you press Start.",
                systemImage: step.icon
            ) {
                recipeCard {
                    RecipeReadyFields(
                        store: store,
                        onFix: { fix in handle(fix: fix, store: store) },
                        bakeoff: project.map(BakeoffSection.Context.init(project:)),
                        keptExports: project?.keptExportStore,
                        project: project
                    )
                }
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
