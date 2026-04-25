import Foundation
import SwiftUI

/// Central manager for app features and modules.
/// Allows enabling/disabling major functional blocks for different release stages (e.g., v0.0.1).
@MainActor
class FeatureManager: ObservableObject {
    static let shared = FeatureManager()
    private static let releaseProfileVersion = 23
    private static let workflowV001EnabledTools =
        "files,collection,folder,aggregate,transcribe,catalogue,"
        + "extract_entities,key_people,timeline,keywords,summarize_file,"
        + "describe,rewrite,"
        + "people_extract,dates_extract,rivers_extract,events_extract,"
        + "mines_extract,properties_extract,legal_references_extract,"
        + "keywords_extract"
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
    private var libraryAdvancedViewsEnabledInternal: Bool = false
    @AppStorage("fichero.features.search_advanced_views")
    private var searchAdvancedViewsEnabledInternal: Bool = false
    @AppStorage("fichero.features.library_search_split_layouts")
    private var librarySearchSplitLayoutsEnabledInternal: Bool = false
    @AppStorage("fichero.features.library_filter_toolbar")
    private var libraryFilterToolbarEnabledInternal: Bool = false
    @AppStorage("fichero.features.library_icon_zoom_controls")
    private var libraryIconZoomControlsEnabledInternal: Bool = false

    // MARK: - Advanced Features (Target: v0.1.0+)

    // V2 inspector (Tinderbox-style Display Attributes + Artifact Panels). Off
    // by default during 0.0.2 — opt-in for users who want to try the redesign.
    // Plan: docs/architecture/swiftui/inspector_redesign.md.
    @AppStorage("fichero.features.inspector_v2")
    private var inspectorV2EnabledInternal: Bool = false
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
    @AppStorage("fichero.features.settings_ai_advanced_tab")
    private var settingsAIAdvancedTabEnabledInternal: Bool = false
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
    @AppStorage("fichero.features.release_profile_version")
    private var releaseProfileVersionApplied: Int = 0

    var isInspectorV2Enabled: Bool { allFeaturesEnabled || inspectorV2EnabledInternal }
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
    var isSettingsAIAdvancedTabEnabled: Bool { allFeaturesEnabled || settingsAIAdvancedTabEnabledInternal }
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

    private init() {
        applyReleaseProfileDefaultsIfNeeded()
    }

    /// Reset to v0.0.1 defaults
    func resetToV001() {
        allFeaturesEnabled = false
        libraryAdvancedViewsEnabledInternal = false
        searchEnabledInternal = true
        searchAdvancedViewsEnabledInternal = false
        librarySearchSplitLayoutsEnabledInternal = false
        libraryFilterToolbarEnabledInternal = false
        libraryIconZoomControlsEnabledInternal = false
        workflowsEnabledInternal = true
        workflowEditorAdvancedViewsEnabled = false
        workflowChainsEnabledInternal = false
        batchesEnabledInternal = false
        chatEnabledInternal = false
        agentsEnabledInternal = false
        automationEnabledInternal = false
        mcpEnabledInternal = false
        integrationsEnabledInternal = false
        activityEnabledInternal = true
        settingsGeneralTabEnabledInternal = true
        settingsBackendTabEnabledInternal = true
        settingsModelsTabEnabledInternal = true
        settingsAIAdvancedTabEnabledInternal = false
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
        workflowImportExportEnabledInternal = false
        workflowLangGraphPreviewEnabledInternal = false
        workflowFilesToolbarEnabledInternal = true
        workflowRunOnSelectionEnabledInternal = true
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
