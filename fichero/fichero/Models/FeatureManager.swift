import Foundation
import Observation
import SwiftUI

// swiftlint:disable file_length
// This file holds ~50 persisted feature flags as stored properties (each needing its own
// declaration + didSet persistence hook, issue #3743). All computed accessors and tier/reset
// logic have already been split into FeatureManager+Accessors.swift and FeatureManager+Tiers.swift
// — extensions cannot hold stored properties, so this irreducible stored state stays here.

/// Central manager for app features and modules.
/// Allows enabling/disabling major functional blocks for different release stages (e.g., v0.0.1).
///
/// All persisted flags below were `@AppStorage`-backed under `ObservableObject`. `@Observable`
/// cannot combine with `@AppStorage` (the macro rewrites stored properties into computed ones,
/// and a property wrapper cannot apply to a computed property), so each flag is now a plain
/// stored property that persists via `didSet` and hydrates from `UserDefaults` in `init`. Keys,
/// defaults, and access levels are unchanged from the `@AppStorage` era.
@MainActor
@Observable
class FeatureManager { // swiftlint:disable:this type_body_length
    static let shared = FeatureManager()

    /// Global toggle to override all flags for internal development.
    /// In a production release, this would be hardcoded to false.
    var allFeaturesEnabled: Bool = ProcessInfo.processInfo.environment["FICHERO_ALL_FEATURES"] == "1" {
        didSet { UserDefaults.standard.set(allFeaturesEnabled, forKey: "fichero.features.all_enabled") }
    }

    // MARK: - Core Features (v0.0.1)

    var isLibraryEnabled: Bool = true

    var searchEnabledInternal: Bool = true {
        didSet { UserDefaults.standard.set(searchEnabledInternal, forKey: "fichero.features.search") }
    }
    var libraryAdvancedViewsEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                libraryAdvancedViewsEnabledInternal, forKey: "fichero.features.library_advanced_views"
            )
        }
    }
    var searchAdvancedViewsEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                searchAdvancedViewsEnabledInternal, forKey: "fichero.features.search_advanced_views"
            )
        }
    }
    var librarySearchSplitLayoutsEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                librarySearchSplitLayoutsEnabledInternal, forKey: "fichero.features.library_search_split_layouts"
            )
        }
    }
    var libraryFilterToolbarEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                libraryFilterToolbarEnabledInternal, forKey: "fichero.features.library_filter_toolbar"
            )
        }
    }
    var libraryIconZoomControlsEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                libraryIconZoomControlsEnabledInternal, forKey: "fichero.features.library_icon_zoom_controls"
            )
        }
    }

    // MARK: - Advanced Features (Target: v0.1.0+)

    var workflowsEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(workflowsEnabledInternal, forKey: "fichero.features.workflows") }
    }
    var workflowEditorAdvancedViewsEnabled: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowEditorAdvancedViewsEnabled, forKey: "fichero.features.workflow_editor_advanced_views"
            )
        }
    }
    var workflowChainsEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(workflowChainsEnabledInternal, forKey: "fichero.features.workflow_chains")
        }
    }
    var batchesEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(batchesEnabledInternal, forKey: "fichero.features.batches") }
    }
    var chatEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(chatEnabledInternal, forKey: "fichero.features.chat") }
    }
    var agentsEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(agentsEnabledInternal, forKey: "fichero.features.agents") }
    }
    var automationEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(automationEnabledInternal, forKey: "fichero.features.automation") }
    }
    var mcpEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(mcpEnabledInternal, forKey: "fichero.features.mcp") }
    }
    var integrationsEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(integrationsEnabledInternal, forKey: "fichero.features.integrations") }
    }
    var activityEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(activityEnabledInternal, forKey: "fichero.features.activity") }
    }
    var settingsGeneralTabEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                settingsGeneralTabEnabledInternal, forKey: "fichero.features.settings_general_tab"
            )
        }
    }
    var settingsBackendTabEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                settingsBackendTabEnabledInternal, forKey: "fichero.features.settings_backend_tab"
            )
        }
    }
    var settingsModelsTabEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                settingsModelsTabEnabledInternal, forKey: "fichero.features.settings_models_tab"
            )
        }
    }
    var settingsEngineTabEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                settingsEngineTabEnabledInternal, forKey: "fichero.features.settings_engine_tab"
            )
        }
    }
    var settingsShareTabEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(settingsShareTabEnabledInternal, forKey: "fichero.features.settings_share_tab")
        }
    }
    var settingsUsersTabEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(settingsUsersTabEnabledInternal, forKey: "fichero.features.settings_users_tab")
        }
    }
    var settingsCaptureTabEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                settingsCaptureTabEnabledInternal, forKey: "fichero.features.settings_capture_tab"
            )
        }
    }
    var workflowToolsMCPEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(workflowToolsMCPEnabledInternal, forKey: "fichero.features.workflow_tools_mcp")
        }
    }
    var workflowToolsAgentsEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsAgentsEnabledInternal, forKey: "fichero.features.workflow_tools_agents"
            )
        }
    }
    var workflowToolsAudioEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsAudioEnabledInternal, forKey: "fichero.features.workflow_tools_audio"
            )
        }
    }
    var workflowToolsVideoEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsVideoEnabledInternal, forKey: "fichero.features.workflow_tools_video"
            )
        }
    }
    var workflowToolsTransformEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsTransformEnabledInternal, forKey: "fichero.features.workflow_tools_transform"
            )
        }
    }
    var workflowToolsConvertEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsConvertEnabledInternal, forKey: "fichero.features.workflow_tools_convert"
            )
        }
    }
    var workflowToolsLogicEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsLogicEnabledInternal, forKey: "fichero.features.workflow_tools_logic"
            )
        }
    }
    var workflowToolsOutputsEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsOutputsEnabledInternal, forKey: "fichero.features.workflow_tools_outputs"
            )
        }
    }
    var workflowToolsFilesEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsFilesEnabledInternal, forKey: "fichero.features.workflow_tools_files"
            )
        }
    }
    var workflowToolsSearchEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowToolsSearchEnabledInternal, forKey: "fichero.features.workflow_tools_search"
            )
        }
    }
    var workflowEnabledToolsInternal: String = "" {
        didSet {
            UserDefaults.standard.set(workflowEnabledToolsInternal, forKey: "fichero.features.workflow_enabled_tools")
        }
    }
    var providersExtendedEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(providersExtendedEnabledInternal, forKey: "fichero.features.providers_extended")
        }
    }
    var workflowImportExportEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowImportExportEnabledInternal, forKey: "fichero.features.workflow_import_export"
            )
        }
    }
    var workflowLangGraphPreviewEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowLangGraphPreviewEnabledInternal, forKey: "fichero.features.workflow_langgraph_preview"
            )
        }
    }
    var workflowFilesToolbarEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowFilesToolbarEnabledInternal, forKey: "fichero.features.workflow_files_toolbar_button"
            )
        }
    }
    var workflowRunOnSelectionEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                workflowRunOnSelectionEnabledInternal, forKey: "fichero.features.workflow_run_on_selection"
            )
        }
    }
    var pdfScrollGridSyncEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(pdfScrollGridSyncEnabledInternal, forKey: "fichero.features.pdf_scroll_grid_sync")
        }
    }
    var claimHighlightSyncEnabledInternal: Bool = false {
        didSet {
            UserDefaults.standard.set(
                claimHighlightSyncEnabledInternal, forKey: "fichero.features.claim_highlight_sync"
            )
        }
    }
    var workspaceModeEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(workspaceModeEnabledInternal, forKey: "fichero.features.workspace_mode") }
    }
    var spatialModeEnabledInternal: Bool = false {
        didSet { UserDefaults.standard.set(spatialModeEnabledInternal, forKey: "fichero.features.spatial_mode") }
    }
    /// Route the 2D `.canvas` view mode to the RealityKit-ortho renderer
    /// (`CanvasSceneView`, #3083). ON by default (#3087 cutover): it shares
    /// `CanvasSceneState` with the 3D renderer. The SwiftUI `Spatial2DCanvas`
    /// stays in `Canvas/2D/Legacy/` as the revert path (toggle this off).
    var canvasRealityKit2DEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                canvasRealityKit2DEnabledInternal, forKey: "fichero.features.canvas_realitykit_2d"
            )
        }
    }
    /// Route the 3D `.space` view mode to the contract-based RealityKit renderer
    /// (`CanvasSpaceView`, #3104). ON by default (#3087 cutover). The `SpaceSceneView`
    /// legacy renderer stays in `Canvas/3D/Legacy/` as the revert path (toggle off).
    var canvasRealityKit3DEnabledInternal: Bool = true {
        didSet {
            UserDefaults.standard.set(
                canvasRealityKit3DEnabledInternal, forKey: "fichero.features.canvas_realitykit_3d"
            )
        }
    }
    var researchEnabledInternal: Bool = true {
        didSet { UserDefaults.standard.set(researchEnabledInternal, forKey: "fichero.features.research") }
    }
    var knowledgeGraphEnabledInternal: Bool = true {
        didSet { UserDefaults.standard.set(knowledgeGraphEnabledInternal, forKey: "fichero.features.knowledge_graph") }
    }
    var firstRunCompleted: Bool = false {
        didSet { UserDefaults.standard.set(firstRunCompleted, forKey: "fichero.first_run.completed") }
    }
    var releaseProfileVersionApplied: Int = 0 {
        didSet {
            UserDefaults.standard.set(
                releaseProfileVersionApplied, forKey: "fichero.features.release_profile_version"
            )
        }
    }

    /// Test-only tier override (production leaves this nil). The baked-in bundle
    /// FicheroFeatureTier is authoritative in real builds and intentionally wins
    /// over any FICHERO_FEATURE_TIER env var — release gating must not be
    /// unlockable via the environment. Tests set this to exercise a specific tier
    /// without weakening that production resolution.
    var testTierOverride: FeatureTier?

    // swiftlint:disable:next function_body_length
    private init() {
        let defaults = UserDefaults.standard
        allFeaturesEnabled = (defaults.object(forKey: "fichero.features.all_enabled") as? Bool)
            ?? (ProcessInfo.processInfo.environment["FICHERO_ALL_FEATURES"] == "1")
        searchEnabledInternal = (defaults.object(forKey: "fichero.features.search") as? Bool) ?? true
        libraryAdvancedViewsEnabledInternal =
            (defaults.object(forKey: "fichero.features.library_advanced_views") as? Bool) ?? true
        searchAdvancedViewsEnabledInternal =
            (defaults.object(forKey: "fichero.features.search_advanced_views") as? Bool) ?? true
        librarySearchSplitLayoutsEnabledInternal =
            (defaults.object(forKey: "fichero.features.library_search_split_layouts") as? Bool) ?? true
        libraryFilterToolbarEnabledInternal =
            (defaults.object(forKey: "fichero.features.library_filter_toolbar") as? Bool) ?? false
        libraryIconZoomControlsEnabledInternal =
            (defaults.object(forKey: "fichero.features.library_icon_zoom_controls") as? Bool) ?? false

        workflowsEnabledInternal = (defaults.object(forKey: "fichero.features.workflows") as? Bool) ?? false
        workflowEditorAdvancedViewsEnabled =
            (defaults.object(forKey: "fichero.features.workflow_editor_advanced_views") as? Bool) ?? false
        workflowChainsEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_chains") as? Bool) ?? false
        batchesEnabledInternal = (defaults.object(forKey: "fichero.features.batches") as? Bool) ?? false
        chatEnabledInternal = (defaults.object(forKey: "fichero.features.chat") as? Bool) ?? false
        agentsEnabledInternal = (defaults.object(forKey: "fichero.features.agents") as? Bool) ?? false
        automationEnabledInternal = (defaults.object(forKey: "fichero.features.automation") as? Bool) ?? false
        mcpEnabledInternal = (defaults.object(forKey: "fichero.features.mcp") as? Bool) ?? false
        integrationsEnabledInternal = (defaults.object(forKey: "fichero.features.integrations") as? Bool) ?? false
        activityEnabledInternal = (defaults.object(forKey: "fichero.features.activity") as? Bool) ?? false
        settingsGeneralTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_general_tab") as? Bool) ?? true
        settingsBackendTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_backend_tab") as? Bool) ?? false
        settingsModelsTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_models_tab") as? Bool) ?? false
        settingsEngineTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_engine_tab") as? Bool) ?? true
        settingsShareTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_share_tab") as? Bool) ?? true
        settingsUsersTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_users_tab") as? Bool) ?? true
        settingsCaptureTabEnabledInternal =
            (defaults.object(forKey: "fichero.features.settings_capture_tab") as? Bool) ?? true
        workflowToolsMCPEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_mcp") as? Bool) ?? false
        workflowToolsAgentsEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_agents") as? Bool) ?? false
        workflowToolsAudioEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_audio") as? Bool) ?? false
        workflowToolsVideoEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_video") as? Bool) ?? false
        workflowToolsTransformEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_transform") as? Bool) ?? false
        workflowToolsConvertEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_convert") as? Bool) ?? false
        workflowToolsLogicEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_logic") as? Bool) ?? false
        workflowToolsOutputsEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_outputs") as? Bool) ?? false
        workflowToolsFilesEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_files") as? Bool) ?? false
        workflowToolsSearchEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_tools_search") as? Bool) ?? false
        workflowEnabledToolsInternal =
            (defaults.object(forKey: "fichero.features.workflow_enabled_tools") as? String) ?? ""
        providersExtendedEnabledInternal =
            (defaults.object(forKey: "fichero.features.providers_extended") as? Bool) ?? false
        workflowImportExportEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_import_export") as? Bool) ?? false
        workflowLangGraphPreviewEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_langgraph_preview") as? Bool) ?? false
        workflowFilesToolbarEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_files_toolbar_button") as? Bool) ?? false
        workflowRunOnSelectionEnabledInternal =
            (defaults.object(forKey: "fichero.features.workflow_run_on_selection") as? Bool) ?? false
        pdfScrollGridSyncEnabledInternal =
            (defaults.object(forKey: "fichero.features.pdf_scroll_grid_sync") as? Bool) ?? false
        claimHighlightSyncEnabledInternal =
            (defaults.object(forKey: "fichero.features.claim_highlight_sync") as? Bool) ?? false
        workspaceModeEnabledInternal =
            (defaults.object(forKey: "fichero.features.workspace_mode") as? Bool) ?? false
        spatialModeEnabledInternal =
            (defaults.object(forKey: "fichero.features.spatial_mode") as? Bool) ?? false
        canvasRealityKit2DEnabledInternal =
            (defaults.object(forKey: "fichero.features.canvas_realitykit_2d") as? Bool) ?? true
        canvasRealityKit3DEnabledInternal =
            (defaults.object(forKey: "fichero.features.canvas_realitykit_3d") as? Bool) ?? true
        researchEnabledInternal = (defaults.object(forKey: "fichero.features.research") as? Bool) ?? true
        knowledgeGraphEnabledInternal =
            (defaults.object(forKey: "fichero.features.knowledge_graph") as? Bool) ?? true
        firstRunCompleted = (defaults.object(forKey: "fichero.first_run.completed") as? Bool) ?? false
        releaseProfileVersionApplied =
            (defaults.object(forKey: "fichero.features.release_profile_version") as? Int) ?? 0

        if UserDefaults.standard.bool(forKey: "hasCompletedOnboarding") {
            firstRunCompleted = true
        }
        applyReleaseProfileDefaultsIfNeeded()
    }
}
