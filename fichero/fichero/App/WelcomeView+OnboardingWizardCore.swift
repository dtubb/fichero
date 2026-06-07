import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - OnboardingWizardView
//
// First-launch wizard. Three screens:
//   1. Welcome — what Fichero is.
//   2. Choose where AI runs — Apple Intelligence / Local / Cloud.
//   3. Setup — varies by choice.
//
// Lives here (not its own file) per the project's "no pbxproj edit" rule:
// new .swift files under fichero/fichero/ need pbxproj entries; appending
// into an existing target file avoids the round-trip.

/// Provider category the user picks on screen 2.
enum OnboardingChoice: String, Identifiable {
    case apple
    case local
    case cloud
    var id: String { rawValue }
}

// Cloud + Local provider lists used to be hardcoded enums here. They've
// been replaced with the engine's `/providers/catalog` so the wizard
// automatically reflects every provider the engine supports — see
// `localCatalog` / `cloudCatalog` accessors on `OnboardingWizardView`.
struct OnboardingWizardView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @Environment(\.dismiss) var dismiss
    @Environment(\.openURL) var openURL

    @State var step: Int = 0
    @State var choice: OnboardingChoice?

    // Catalog-driven provider state. Loaded once from `/providers/catalog`
    // and filtered per category (Apple / Local / Cloud) on the setup step.
    // The user clicks a card to set `selectedProviderType`, which is the
    // single source of truth from then on (key save, defaults, etc.).
    @State var catalog: [Components.Schemas.ProviderCatalogResponse] = []
    @State var isCatalogLoading: Bool = false
    @State var selectedProviderType: String?
    @State var apiKey: String = ""
    @State var serverURL: String = ""

    @State var isSaving: Bool = false
    @State var errorMessage: String?

    // Apple Intelligence availability probe (engine returns {available, reason}).
    @State var appleProbeState: AppleProbeState = .idle
    enum AppleProbeState { case idle, probing, available, unavailable(String) }

    // Local server connectivity check.
    @State var localTestState: LocalTestState = .idle
    enum LocalTestState { case idle, testing, connected(String?), failed(String) }

    /// Default for new imports. Mirrors GeneralSettingsView's
    /// @AppStorage("defaultImportMode"). Default = link.
    @AppStorage("defaultImportMode") var defaultImportMode: String = IngestMode.link.rawValue

    var body: some View {
        VStack(spacing: 0) {
            switch step {
            case 0: welcomeStep
            case 1: chooseStep
            case 2: setupStep
            default: importModeStep
            }
        }
        .frame(width: 560, height: 560)
        .task {
            // Pre-load the catalog so when the user reaches the setup step
            // there's no "loading…" flash. AddProviderSheet does the same
            // thing (see AddProviderSheet+Helpers.loadCatalog).
            await loadCatalog()
        }
    }

    // MARK: - Catalog accessors

    /// All non-builtin local providers (Ollama, LM Studio, …). Sorted by
    /// the catalog's `sort_order`.
    var localCatalog: [Components.Schemas.ProviderCatalogResponse] {
        catalog.filter { $0.isLocal && !$0.isBuiltin }
            .sorted { $0.sortOrder < $1.sortOrder }
    }

    /// All cloud providers. Same sort.
    var cloudCatalog: [Components.Schemas.ProviderCatalogResponse] {
        catalog.filter { !$0.isLocal && !$0.isBuiltin }
            .sorted { $0.sortOrder < $1.sortOrder }
    }

    /// The single Apple-Intelligence catalog entry (if available).
    var appleCatalogEntry: Components.Schemas.ProviderCatalogResponse? {
        catalog.first { $0.isBuiltin }
    }

    /// The currently-selected catalog entry, if any.
    var selectedEntry: Components.Schemas.ProviderCatalogResponse? {
        guard let selectedProviderType else { return nil }
        return catalog.first { $0.providerType == selectedProviderType }
    }

    /// Default server URL for a local provider, mirroring AddProviderSheet's
    /// `defaultServerUrl(for:)` helper. Keep them in sync.
    func defaultServerURL(for providerType: String) -> String {
        switch providerType {
        case "ollama": return "http://localhost:11434"
        case "lmstudio": return "http://localhost:1234"
        default: return ""
        }
    }

    /// Where to send the user when they want to install the local server. Catalog
    /// doesn't carry this, so it's a small per-type table here.
    func installURL(for providerType: String) -> URL? {
        switch providerType {
        case "ollama": return URL(string: "https://ollama.com/download")
        case "lmstudio": return URL(string: "https://lmstudio.ai/")
        default: return nil
        }
    }
}
