import SwiftUI

// MARK: - Set Up a Project's pages (section 7d, ruled 2026-10-11, #5668; source.onboard.project.*)

/// Set Up a Project, one small page per step: Your project, Add material, About the material, Choose the Stages, one
/// page per chosen stage, Train and Ready. Same page chrome and navigation as the app's pages; the fields scroll
/// because a page can be longer than the card. Every page after Your project works on the project's own store.
extension FirstRunWindow {
    @ViewBuilder
    func recipeStepPage(_ step: SetupStep) -> some View {
        if step == .project {
            stepPage(
                title: "Your project",
                subtitle: "Name it and say where it lives; most projects live inside Fichero.",
                systemImage: step.icon
            ) {
                recipeCard(step) { SetupWhereItLivesFields(store: newProject) }
            }
        } else if let store {
            setupPage(step, store: store)
        } else {
            stepPage(title: step.title(), subtitle: "Make the project first.", systemImage: step.icon) {
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private func setupPage(_ step: SetupStep, store: RecipeSetupStore) -> some View {
        switch step {
        case .addMaterial, .aboutMaterial:
            materialPage(step, store: store)
        case .stages, .stage:
            stagePage(step, store: store)
        case .train:
            stepPage(
                title: "Train",
                subtitle: "Teach Fichero your hand. Once you have corrected some pages, it can train a model of your own, here or elsewhere.",
                systemImage: step.icon
            ) {
                recipeCard(step) { RecipeTrainOffersFields(store: store) }
            }
        default:
            stepPage(
                title: "Ready",
                subtitle: "The plan from your answers; nothing runs before you press Start.",
                systemImage: step.icon
            ) {
                recipeCard(step) {
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

    /// Add material and About the material: how it comes in, then what it is (`source.onboard.project.*`).
    @ViewBuilder
    private func materialPage(_ step: SetupStep, store: RecipeSetupStore) -> some View {
        if step == .addMaterial {
            stepPage(
                title: "Add material",
                subtitle: "Add files or folders, and say how they come in.",
                systemImage: step.icon
            ) {
                recipeCard(step) {
                    RecipeMaterialSourceFields(
                        store: store, importer: project?.importService, syncFolders: project?.syncFolderStore,
                        icloud: project?.icloudStore, actionsService: project?.actionsService
                    )
                }
            }
        } else {
            stepPage(
                title: "About the material",
                subtitle: "What it is, when and where it was written, and in which hand.",
                systemImage: step.icon
            ) {
                recipeCard(step) { RecipeAboutFields(store: store) }
            }
        }
    }

    /// Choose the Stages, and one chosen stage's page (`source.onboard.stages.*`).
    @ViewBuilder
    private func stagePage(_ step: SetupStep, store: RecipeSetupStore) -> some View {
        switch step {
        case .stages:
            stepPage(
                title: "Choose the stages",
                subtitle: "Tick each stage of the work this project needs; each has its own page next.",
                systemImage: step.icon
            ) {
                recipeCard(step) { SetupStageChooser(store: store) }
            }
        case .stage(let stageId):
            let stage = store.stage(stageId)
            stepPage(
                title: stage?.title ?? stageId,
                subtitle: stage?.sentence ?? "",
                systemImage: step.icon
            ) {
                recipeCard(step) {
                    if let stage {
                        SetupStagePage(store: store, stage: stage, onFix: { fix in handle(fix: fix, store: store) },
                                       bakeoff: project.map(BakeoffSection.Context.init(project:)), project: project)
                    }
                }
            }
        default:
            EmptyView()
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

    /// What a page's scroll view is keyed on: a page opens at its top, never at the last page's position (#5801).
    static func scrollResetID(for step: SetupStep) -> String { step.id }

    private func recipeCard<Content: View>(_ step: SetupStep, @ViewBuilder _ content: () -> Content) -> some View {
        ScrollView {
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(22)
        }
        // Back, Next or the sidebar: two stage pages share one ScrollView unless each has its own identity.
        .id(Self.scrollResetID(for: step))
        .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        }
    }
}
