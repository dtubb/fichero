import Foundation
import Observation
import OSLog
import SwiftUI

// swiftlint:disable file_length

private let featureManagerLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "FeatureManager"
)

extension FeatureTier {
    var rank: Int { rawValue }

    var environmentValue: String {
        switch self {
        case .dev: return "dev"
        case .alpha: return "alpha"
        case .beta: return "beta"
        case .release: return "release"
        }
    }
}

/// Central manager for app features and modules.
/// Allows enabling/disabling major functional blocks for different release stages (e.g., v0.0.1).
@MainActor
class FeatureManager: ObservableObject { // swiftlint:disable:this type_body_length
    static let shared = FeatureManager()
    // Bumped to re-apply workflow execution release defaults on existing
    // installs (langgraph preview, run-on-selection, files toolbar, import/export).
    private static let releaseProfileVersion = 32
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
    private static var didWarnUnknownFeatureTier = false

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

    var activeBuildTier: FeatureTier {
        if let tier = Self.resolveFeatureTier(
            Bundle.main.infoDictionary?["FicheroFeatureTier"] as? String
        ) {
            return tier
        }
        if let tier = Self.resolveFeatureTier(
            ProcessInfo.processInfo.environment["FICHERO_FEATURE_TIER"]
        ) {
            return tier
        }
        return .dev
    }

    /// Development builds deliberately expose every implemented feature.
    var allFeaturesEffectivelyEnabled: Bool {
        allFeaturesEnabled || activeBuildTier == .dev
    }

    @available(*, deprecated, message: "use activeBuildTier == .dev")
    static var isDevFeatureTier: Bool { shared.activeBuildTier == .dev }

    func isVisible(_ key: FeatureKey) -> Bool {
        FeatureTiers.map[key]!.tier.rank >= activeBuildTier.rank
    }

    private func isEnabled(_ key: FeatureKey, _ enabled: Bool) -> Bool {
        isVisible(key) && (allFeaturesEffectivelyEnabled || enabled)
    }

    var isWorkflowsEnabled: Bool { isEnabled(.workflows, workflowsEnabledInternal) }
    var isSearchEnabled: Bool { isEnabled(.search, searchEnabledInternal) }
    var isWorkflowEditorAdvancedViewsEnabled: Bool {
        isEnabled(.workflowEditorAdvancedViews, workflowEditorAdvancedViewsEnabled)
    }
    var isWorkflowChainsEnabled: Bool { isEnabled(.workflowChains, workflowChainsEnabledInternal) }
    var isBatchesEnabled: Bool { isEnabled(.batches, batchesEnabledInternal) }
    var isChatEnabled: Bool { isEnabled(.chat, chatEnabledInternal) }
    var isAgentsEnabled: Bool { isEnabled(.agents, agentsEnabledInternal) }
    var isAutomationEnabled: Bool { isEnabled(.automation, automationEnabledInternal) }
    var isMCPEnabled: Bool { isEnabled(.mcpUi, mcpEnabledInternal) }
    var isIntegrationsEnabled: Bool { isEnabled(.integrations, integrationsEnabledInternal) }
    var isActivityEnabled: Bool { isEnabled(.activity, activityEnabledInternal) }
    var isLibraryAdvancedViewsEnabled: Bool {
        isEnabled(.libraryAdvancedViews, libraryAdvancedViewsEnabledInternal)
    }
    var isSearchAdvancedViewsEnabled: Bool {
        isEnabled(.searchAdvancedViews, searchAdvancedViewsEnabledInternal)
    }
    var isLibrarySearchSplitLayoutsEnabled: Bool {
        isEnabled(.librarySearchSplitLayouts, librarySearchSplitLayoutsEnabledInternal)
    }
    var isLibraryFilterToolbarEnabled: Bool {
        isEnabled(.libraryFilterToolbar, libraryFilterToolbarEnabledInternal)
    }
    var isLibraryIconZoomControlsEnabled: Bool {
        isEnabled(.libraryIconZoomControls, libraryIconZoomControlsEnabledInternal)
    }
    var isSettingsGeneralTabEnabled: Bool {
        isEnabled(.settingsGeneralTab, settingsGeneralTabEnabledInternal)
    }
    var isSettingsBackendTabEnabled: Bool {
        isEnabled(.settingsBackendTab, settingsBackendTabEnabledInternal)
    }
    var isSettingsModelsTabEnabled: Bool {
        isEnabled(.settingsModelsTab, settingsModelsTabEnabledInternal)
    }
    var isSettingsEngineTabEnabled: Bool {
        isEnabled(.settingsEngineTab, settingsEngineTabEnabledInternal)
    }
    var isSettingsShareTabEnabled: Bool {
        isEnabled(.settingsShareTab, settingsShareTabEnabledInternal)
    }
    var isSettingsUsersTabEnabled: Bool {
        isEnabled(.settingsUsersTab, settingsUsersTabEnabledInternal)
    }
    var isSettingsCaptureTabEnabled: Bool {
        isEnabled(.settingsCaptureTab, settingsCaptureTabEnabledInternal)
    }
    var isWorkflowToolsMCPEnabled: Bool {
        isEnabled(.workflowToolsMcp, workflowToolsMCPEnabledInternal)
    }
    var isWorkflowToolsAgentsEnabled: Bool {
        isEnabled(.workflowToolsAgents, workflowToolsAgentsEnabledInternal)
    }
    var isWorkflowToolsAudioEnabled: Bool {
        isEnabled(.workflowToolsAudio, workflowToolsAudioEnabledInternal)
    }
    var isWorkflowToolsVideoEnabled: Bool {
        isEnabled(.workflowToolsVideo, workflowToolsVideoEnabledInternal)
    }
    var isWorkflowToolsTransformEnabled: Bool {
        isEnabled(.workflowToolsTransform, workflowToolsTransformEnabledInternal)
    }
    var isWorkflowToolsConvertEnabled: Bool {
        isEnabled(.workflowToolsConvert, workflowToolsConvertEnabledInternal)
    }
    var isWorkflowToolsLogicEnabled: Bool {
        isEnabled(.workflowToolsLogic, workflowToolsLogicEnabledInternal)
    }
    var isWorkflowToolsOutputsEnabled: Bool {
        isEnabled(.workflowToolsOutputs, workflowToolsOutputsEnabledInternal)
    }
    var isWorkflowToolsFilesEnabled: Bool {
        isEnabled(.workflowToolsFiles, workflowToolsFilesEnabledInternal)
    }
    var isWorkflowToolsSearchEnabled: Bool {
        isEnabled(.workflowToolsSearch, workflowToolsSearchEnabledInternal)
    }
    var isProvidersExtendedEnabled: Bool {
        isEnabled(.providersExtended, providersExtendedEnabledInternal)
    }
    var isProvidersEnabled: Bool {
        isVisible(.providers)
            && (allFeaturesEnabled || providersExtendedEnabledInternal || activeBuildTier == .dev)
    }
    var isWorkflowImportExportEnabled: Bool {
        isEnabled(.workflowImportExport, workflowImportExportEnabledInternal)
    }
    var isWorkflowLangGraphPreviewEnabled: Bool {
        isEnabled(.workflowLangGraphPreview, workflowLangGraphPreviewEnabledInternal)
    }
    var isWorkflowFilesToolbarButtonEnabled: Bool {
        isEnabled(.workflowImportExport, workflowFilesToolbarEnabledInternal)
    }
    var isWorkflowRunOnSelectionEnabled: Bool {
        isEnabled(.workflowRunOnSelection, workflowRunOnSelectionEnabledInternal)
    }
    var workflowEnabledTools: Set<String> {
        Set(
            workflowEnabledToolsInternal
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                .filter { !$0.isEmpty }
        )
    }
    /// PDF scroll → grid/inspector sync. Defaulted OFF; enable via Settings or `FICHERO_ALL_FEATURES=1`.
    /// Guards the NSScrollView live-scroll observer added in PDFPageView (#591/#592).
    var isPdfScrollGridSyncEnabled: Bool {
        isEnabled(.pdfScrollGridSync, pdfScrollGridSyncEnabledInternal)
    }
    /// Bidirectional claim highlight sync across PDF, Content, and Inspector panes. Defaulted OFF.
    var isClaimHighlightSyncEnabled: Bool {
        isEnabled(.claimHighlightSync, claimHighlightSyncEnabledInternal)
    }
    var isWorkspaceModeEnabled: Bool { isEnabled(.workspaceMode, workspaceModeEnabledInternal) }
    var isSpatialModeEnabled: Bool { isEnabled(.spatialMode, spatialModeEnabledInternal) }
    var isCanvasRealityKit2DEnabled: Bool {
        isEnabled(.canvasRealityKit2D, canvasRealityKit2DEnabledInternal)
    }
    var isCanvasRealityKit3DEnabled: Bool {
        isEnabled(.canvasRealityKit3D, canvasRealityKit3DEnabledInternal)
    }
    var isResearchEnabled: Bool { isEnabled(.research, researchEnabledInternal) }
    /// Knowledge Graph / Ontology browser (#498). Defaulted ON — the view is complete.
    var isKnowledgeGraphEnabled: Bool {
        isEnabled(.knowledgeGraph, knowledgeGraphEnabledInternal)
    }

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
        mcpEnabledInternal = true
        integrationsEnabledInternal = true
        activityEnabledInternal = true

        settingsGeneralTabEnabledInternal = true
        settingsBackendTabEnabledInternal = true
        settingsModelsTabEnabledInternal = true
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
        if allFeaturesEffectivelyEnabled {
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

    private static func resolveFeatureTier(_ rawValue: String?) -> FeatureTier? {
        guard let rawValue else {
            return nil
        }
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalized.isEmpty else {
            return nil
        }

        switch normalized {
        case "dev":
            return .dev
        case "alpha":
            return .alpha
        case "beta":
            return .beta
        case "release":
            return .release
        default:
            warnUnknownFeatureTierOnce(rawValue)
            return .dev
        }
    }

    private static func warnUnknownFeatureTierOnce(_ rawValue: String) {
        guard !didWarnUnknownFeatureTier else {
            return
        }
        didWarnUnknownFeatureTier = true
        featureManagerLogger.warning(
            "Unknown FICHERO_FEATURE_TIER value '\(rawValue, privacy: .public)'; defaulting to dev"
        )
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
@Observable
class ClaimFocusState {
    static let shared = ClaimFocusState()

    var selectedClaimId: String?
    var selectedClaimText: String?
    var selectedClaimSourceDocumentId: String?
    var selectedClaimPageLabel: String?
    var selectedClaimCharStart: Int?
    var selectedClaimCharEnd: Int?

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
