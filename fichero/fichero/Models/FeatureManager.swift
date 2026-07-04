import Foundation
import SwiftUI

/// Central manager for app features and modules.
/// Allows enabling/disabling major functional blocks for different release stages (e.g., v0.0.1).
@MainActor
class FeatureManager: ObservableObject {
    static let shared = FeatureManager()
    // Bumped to re-apply workflow execution release defaults on existing
    // installs (langgraph preview, run-on-selection, files toolbar, import/export).
    private static let releaseProfileVersion = 31
    private static let workflowV001EnabledTools =
        "files,collection,folder,aggregate,transcribe,catalogue,"
        + "extract_all,kg_writer,extract_entities,key_people,timeline,keywords,summarize_file,"
        + "describe,rewrite,"
        + "citations_extract,"
        + "people_extract,dates_extract,rivers_extract,events_extract,"
        + "mines_extract,properties_extract,legal_references_extract,"
        + "keywords_extract,quotes_extract,"
        + "people_folder_cleanup,places_folder_cleanup,organizations_folder_cleanup,"
        + "dates_folder_cleanup,events_folder_cleanup,keywords_folder_cleanup"
    private static let isDevFeatureTier =
        ProcessInfo.processInfo.environment["FICHERO_FEATURE_TIER"]?.lowercased() == "dev"

    /// Global toggle to override all flags for internal development.
    /// In a production release, this would be hardcoded to false.
    @AppStorage("fichero.features.all_enabled")
    var allFeaturesEnabled: Bool =
        ProcessInfo.processInfo.environment["FICHERO_ALL_FEATURES"] == "1"

    // MARK: - Core Features (v0.0.1)

    @Published var isLibraryEnabled: Bool = true
    @AppStorage("fichero.features.search")
    private var searchEnabledInternal: Bool = true
    @AppStorage("fichero.features.library_advanced_views")
    private var libraryAdvancedViewsEnabledInternal: Bool = true
    @AppStorage("fichero.features.search_advanced_views")
    private var searchAdvancedViewsEnabledInternal: Bool = true
    @AppStorage("fichero.features.library_search_split_layouts")
    private var librarySearchSplitLayoutsEnabledInternal: Bool = true
    @AppStorage("fichero.features.library_filter_toolbar")
    private var libraryFilterToolbarEnabledInternal: Bool = false
    @AppStorage("fichero.features.library_icon_zoom_controls")
    private var libraryIconZoomControlsEnabledInternal: Bool = false

    // MARK: - Advanced Features (Target: v0.1.0+)

    @AppStorage("fichero.features.workflows") private var workflowsEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_editor_advanced_views")
    private var workflowEditorAdvancedViewsEnabled: Bool = false
    @AppStorage("fichero.features.workflow_chains")
    private var workflowChainsEnabledInternal: Bool = false
    @AppStorage("fichero.features.batches") private var batchesEnabledInternal: Bool = false
    @AppStorage("fichero.features.chat") private var chatEnabledInternal: Bool = false
    @AppStorage("fichero.features.agents") private var agentsEnabledInternal: Bool = false
    @AppStorage("fichero.features.automation") private var automationEnabledInternal: Bool = false
    @AppStorage("fichero.features.mcp") private var mcpEnabledInternal: Bool = false
    @AppStorage("fichero.features.integrations") private var integrationsEnabledInternal: Bool = false
    @AppStorage("fichero.features.activity") private var activityEnabledInternal: Bool = false
    @AppStorage("fichero.features.settings_general_tab")
    private var settingsGeneralTabEnabledInternal: Bool = true
    @AppStorage("fichero.features.settings_backend_tab")
    private var settingsBackendTabEnabledInternal: Bool = false
    @AppStorage("fichero.features.settings_models_tab")
    private var settingsModelsTabEnabledInternal: Bool = false
    @AppStorage("fichero.features.settings_engine_tab")
    private var settingsEngineTabEnabledInternal: Bool = true
    @AppStorage("fichero.features.settings_share_tab")
    private var settingsShareTabEnabledInternal: Bool = true
    @AppStorage("fichero.features.settings_users_tab")
    private var settingsUsersTabEnabledInternal: Bool = true
    @AppStorage("fichero.features.settings_capture_tab")
    private var settingsCaptureTabEnabledInternal: Bool = true
    @AppStorage("fichero.features.workflow_tools_mcp")
    private var workflowToolsMCPEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_agents")
    private var workflowToolsAgentsEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_audio")
    private var workflowToolsAudioEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_video")
    private var workflowToolsVideoEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_transform")
    private var workflowToolsTransformEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_convert")
    private var workflowToolsConvertEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_logic")
    private var workflowToolsLogicEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_outputs")
    private var workflowToolsOutputsEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_files")
    private var workflowToolsFilesEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_tools_search")
    private var workflowToolsSearchEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_enabled_tools")
    private var workflowEnabledToolsInternal: String = ""
    @AppStorage("fichero.features.providers_extended")
    private var providersExtendedEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_import_export")
    private var workflowImportExportEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_langgraph_preview")
    private var workflowLangGraphPreviewEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_files_toolbar_button")
    private var workflowFilesToolbarEnabledInternal: Bool = false
    @AppStorage("fichero.features.workflow_run_on_selection")
    private var workflowRunOnSelectionEnabledInternal: Bool = false
    @AppStorage("fichero.features.pdf_scroll_grid_sync")
    private var pdfScrollGridSyncEnabledInternal: Bool = false
    @AppStorage("fichero.features.claim_highlight_sync")
    private var claimHighlightSyncEnabledInternal: Bool = false
    @AppStorage("fichero.features.workspace_mode")
    private var workspaceModeEnabledInternal: Bool = false
    @AppStorage("fichero.features.spatial_mode")
    private var spatialModeEnabledInternal: Bool = false
    /// Route the 2D `.canvas` view mode to the new RealityKit-ortho renderer
    /// (`CanvasSceneView`, #3083) instead of the SwiftUI `Spatial2DCanvas`. Off
    /// by default; the SwiftUI canvas is retired only at cutover (#3087).
    @AppStorage("fichero.features.canvas_realitykit_2d")
    private var canvasRealityKit2DEnabledInternal: Bool = false
    /// Route the 3D `.space` view mode to the new contract-based RealityKit
    /// renderer (`CanvasSpaceView`, #3104) instead of the #3088 `SpaceSceneView`.
    /// Off by default; #3088 stays the stepping-stone until cutover (#3087).
    @AppStorage("fichero.features.canvas_realitykit_3d")
    private var canvasRealityKit3DEnabledInternal: Bool = false
    @AppStorage("fichero.features.research") private var researchEnabledInternal: Bool = true
    @AppStorage("fichero.features.knowledge_graph") private var knowledgeGraphEnabledInternal: Bool = true
    @AppStorage("fichero.first_run.completed") var firstRunCompleted: Bool = false
    @AppStorage("fichero.features.release_profile_version")
    private var releaseProfileVersionApplied: Int = 0

    var isWorkflowsEnabled: Bool { allFeaturesEnabled || workflowsEnabledInternal }
    var isSearchEnabled: Bool { allFeaturesEnabled || searchEnabledInternal }
    var isWorkflowEditorAdvancedViewsEnabled: Bool {
        allFeaturesEnabled || workflowEditorAdvancedViewsEnabled
    }
    var isWorkflowChainsEnabled: Bool { allFeaturesEnabled || workflowChainsEnabledInternal }
    var isBatchesEnabled: Bool { allFeaturesEnabled || batchesEnabledInternal }
    var isChatEnabled: Bool { allFeaturesEnabled || chatEnabledInternal }
    var isAgentsEnabled: Bool { allFeaturesEnabled || agentsEnabledInternal }
    var isAutomationEnabled: Bool { allFeaturesEnabled || automationEnabledInternal }
    var isMCPEnabled: Bool { allFeaturesEnabled || mcpEnabledInternal }
    var isIntegrationsEnabled: Bool { allFeaturesEnabled || integrationsEnabledInternal }
    var isActivityEnabled: Bool { allFeaturesEnabled || activityEnabledInternal }
    var isLibraryAdvancedViewsEnabled: Bool {
        allFeaturesEnabled || libraryAdvancedViewsEnabledInternal
    }
    var isSearchAdvancedViewsEnabled: Bool { allFeaturesEnabled || searchAdvancedViewsEnabledInternal }
    var isLibrarySearchSplitLayoutsEnabled: Bool {
        allFeaturesEnabled || librarySearchSplitLayoutsEnabledInternal
    }
    var isLibraryFilterToolbarEnabled: Bool { allFeaturesEnabled || libraryFilterToolbarEnabledInternal }
    var isLibraryIconZoomControlsEnabled: Bool {
        allFeaturesEnabled || libraryIconZoomControlsEnabledInternal
    }
    var isSettingsGeneralTabEnabled: Bool { allFeaturesEnabled || settingsGeneralTabEnabledInternal }
    var isSettingsBackendTabEnabled: Bool { allFeaturesEnabled || settingsBackendTabEnabledInternal }
    var isSettingsModelsTabEnabled: Bool { allFeaturesEnabled || settingsModelsTabEnabledInternal }
    var isSettingsEngineTabEnabled: Bool { allFeaturesEnabled || settingsEngineTabEnabledInternal }
    var isSettingsShareTabEnabled: Bool { allFeaturesEnabled || settingsShareTabEnabledInternal }
    var isSettingsUsersTabEnabled: Bool { allFeaturesEnabled || settingsUsersTabEnabledInternal }
    var isSettingsCaptureTabEnabled: Bool { allFeaturesEnabled || settingsCaptureTabEnabledInternal }
    var isWorkflowToolsMCPEnabled: Bool { allFeaturesEnabled || workflowToolsMCPEnabledInternal }
    var isWorkflowToolsAgentsEnabled: Bool { allFeaturesEnabled || workflowToolsAgentsEnabledInternal }
    var isWorkflowToolsAudioEnabled: Bool { allFeaturesEnabled || workflowToolsAudioEnabledInternal }
    var isWorkflowToolsVideoEnabled: Bool { allFeaturesEnabled || workflowToolsVideoEnabledInternal }
    var isWorkflowToolsTransformEnabled: Bool { allFeaturesEnabled || workflowToolsTransformEnabledInternal }
    var isWorkflowToolsConvertEnabled: Bool { allFeaturesEnabled || workflowToolsConvertEnabledInternal }
    var isWorkflowToolsLogicEnabled: Bool { allFeaturesEnabled || workflowToolsLogicEnabledInternal }
    var isWorkflowToolsOutputsEnabled: Bool { allFeaturesEnabled || workflowToolsOutputsEnabledInternal }
    var isWorkflowToolsFilesEnabled: Bool { allFeaturesEnabled || workflowToolsFilesEnabledInternal }
    var isWorkflowToolsSearchEnabled: Bool { allFeaturesEnabled || workflowToolsSearchEnabledInternal }
    var workflowEnabledTools: Set<String> {
        Set(
            workflowEnabledToolsInternal
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                .filter { !$0.isEmpty }
        )
    }
    var isProvidersExtendedEnabled: Bool { allFeaturesEnabled || providersExtendedEnabledInternal }
    var isProvidersEnabled: Bool {
        allFeaturesEnabled || providersExtendedEnabledInternal || Self.isDevFeatureTier
    }
    var isWorkflowImportExportEnabled: Bool { allFeaturesEnabled || workflowImportExportEnabledInternal }
    var isWorkflowLangGraphPreviewEnabled: Bool {
        allFeaturesEnabled || workflowLangGraphPreviewEnabledInternal
    }
    var isWorkflowFilesToolbarButtonEnabled: Bool { allFeaturesEnabled || workflowFilesToolbarEnabledInternal }
    var isWorkflowRunOnSelectionEnabled: Bool {
        allFeaturesEnabled || workflowRunOnSelectionEnabledInternal
    }
    /// PDF scroll → grid/inspector sync. Defaulted OFF; enable via Settings or `FICHERO_ALL_FEATURES=1`.
    /// Guards the NSScrollView live-scroll observer added in PDFPageView (#591/#592).
    var isPdfScrollGridSyncEnabled: Bool { allFeaturesEnabled || pdfScrollGridSyncEnabledInternal }
    /// Bidirectional claim highlight sync across PDF, Content, and Inspector panes. Defaulted OFF.
    var isClaimHighlightSyncEnabled: Bool { allFeaturesEnabled || claimHighlightSyncEnabledInternal }
    var isWorkspaceModeEnabled: Bool { allFeaturesEnabled || workspaceModeEnabledInternal }
    var isSpatialModeEnabled: Bool { allFeaturesEnabled || spatialModeEnabledInternal }
    var isCanvasRealityKit2DEnabled: Bool { allFeaturesEnabled || canvasRealityKit2DEnabledInternal }
    var isCanvasRealityKit3DEnabled: Bool { allFeaturesEnabled || canvasRealityKit3DEnabledInternal }
    var isResearchEnabled: Bool { allFeaturesEnabled || researchEnabledInternal }
    /// Knowledge Graph / Ontology browser (#498). Defaulted ON — the view is complete.
    var isKnowledgeGraphEnabled: Bool { allFeaturesEnabled || knowledgeGraphEnabledInternal }

    private init() {
        if UserDefaults.standard.bool(forKey: "hasCompletedOnboarding") {
            firstRunCompleted = true
        }
        applyReleaseProfileDefaultsIfNeeded()
    }

    /// Reset to v0.0.1 defaults
    func resetToV001() {
        allFeaturesEnabled = false
        libraryAdvancedViewsEnabledInternal = true   // 0.0.3 #517: list/table/map re-enabled
        searchEnabledInternal = true
        searchAdvancedViewsEnabledInternal = true    // 0.0.3 #517: search results in all views
        librarySearchSplitLayoutsEnabledInternal = false
        libraryFilterToolbarEnabledInternal = false
        libraryIconZoomControlsEnabledInternal = true // 0.0.3 #517: zoom controls re-enabled
        workflowsEnabledInternal = true
        workflowEditorAdvancedViewsEnabled = true
        workflowChainsEnabledInternal = true
        batchesEnabledInternal = true
        chatEnabledInternal = false
        agentsEnabledInternal = false
        automationEnabledInternal = false
        mcpEnabledInternal = false
        integrationsEnabledInternal = false
        activityEnabledInternal = true

        settingsGeneralTabEnabledInternal = true
        settingsBackendTabEnabledInternal = false
        settingsModelsTabEnabledInternal = false
        settingsEngineTabEnabledInternal = true
        settingsShareTabEnabledInternal = true
        settingsUsersTabEnabledInternal = true
        settingsCaptureTabEnabledInternal = true
        workflowToolsMCPEnabledInternal = false
        workflowToolsAgentsEnabledInternal = false
        workflowToolsAudioEnabledInternal = false
        workflowToolsVideoEnabledInternal = false
        workflowToolsTransformEnabledInternal = false
        workflowToolsConvertEnabledInternal = false
        workflowToolsLogicEnabledInternal = false
        workflowToolsOutputsEnabledInternal = false
        workflowToolsFilesEnabledInternal = true
        workflowToolsSearchEnabledInternal = false
        workflowEnabledToolsInternal = Self.workflowV001EnabledTools
        providersExtendedEnabledInternal = false
        workflowImportExportEnabledInternal = true
        workflowLangGraphPreviewEnabledInternal = true
        workflowFilesToolbarEnabledInternal = true
        workflowRunOnSelectionEnabledInternal = true
        workspaceModeEnabledInternal = false
        spatialModeEnabledInternal = false
        canvasRealityKit2DEnabledInternal = false
        canvasRealityKit3DEnabledInternal = false
        researchEnabledInternal = true
        knowledgeGraphEnabledInternal = true
        releaseProfileVersionApplied = Self.releaseProfileVersion
    }

    func isWorkflowToolExplicitlyEnabled(_ toolName: String) -> Bool {
        if allFeaturesEnabled {
            return true
        }
        let normalized = normalizeWorkflowToolName(toolName)
        return workflowEnabledTools.contains(normalized)
    }

    private func applyReleaseProfileDefaultsIfNeeded() {
        if releaseProfileVersionApplied < 15 {
            let currentTools = workflowEnabledToolsInternal
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if currentTools.isEmpty {
                workflowEnabledToolsInternal = Self.workflowV001EnabledTools
            }
        }

        guard releaseProfileVersionApplied < Self.releaseProfileVersion else {
            return
        }
        resetToV001()
    }

    private func normalizeWorkflowToolName(_ toolName: String) -> String {
        switch toolName.lowercased() {
        case "folder", "container":
            return "collection"
        default:
            return toolName.lowercased()
        }
    }
}

// MARK: - View Helpers

extension View {
    /// Conditionally shows a view based on a feature flag
    @ViewBuilder
    func featureEnabled(_ isEnabled: Bool) -> some View {
        if isEnabled {
            self
        }
    }
}

// MARK: - ClaimFocusState

/// Observable state for bidirectional claim highlighting across PDF, Content, and Inspector panes.
@MainActor
class ClaimFocusState: ObservableObject {
    static let shared = ClaimFocusState()

    @Published var selectedClaimId: String?
    @Published var selectedClaimText: String?
    @Published var selectedClaimSourceDocumentId: String?
    @Published var selectedClaimPageLabel: String?
    @Published var selectedClaimCharStart: Int?
    @Published var selectedClaimCharEnd: Int?

    func selectClaim(
        claimId: String,
        claimText: String? = nil,
        sourceDocumentId: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        selectedClaimId = claimId
        selectedClaimText = claimText
        selectedClaimSourceDocumentId = sourceDocumentId
        selectedClaimPageLabel = pageLabel
        selectedClaimCharStart = charStart
        selectedClaimCharEnd = charEnd
        NotificationCenter.default.post(name: .claimFocusChanged, object: self)
    }

    func clearSelection() {
        selectedClaimId = nil
        selectedClaimText = nil
        selectedClaimSourceDocumentId = nil
        selectedClaimPageLabel = nil
        selectedClaimCharStart = nil
        selectedClaimCharEnd = nil
        NotificationCenter.default.post(name: .claimFocusChanged, object: self)
    }

    func isClaimSelected(_ claimId: String) -> Bool { selectedClaimId == claimId }

    /// Synchronize claim focus across all panes (PDF, Content, Inspector)
    /// This method ensures that when a claim is selected in one pane,
    /// it's properly synced to all other panes for a unified experience
    func syncClaimFocus(
        to documentId: String,
        claimId: String,
        claimText: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        // Select the claim across all panes
        selectClaim(
            claimId: claimId,
            claimText: claimText,
            sourceDocumentId: documentId,
            pageLabel: pageLabel,
            charStart: charStart,
            charEnd: charEnd
        )
    }
}

extension Notification.Name {
    static let claimFocusChanged = Notification.Name("claimFocusChanged")
}
