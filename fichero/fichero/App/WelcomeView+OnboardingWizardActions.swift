import FicheroAPIClient
import OSLog
import SwiftUI

extension OnboardingWizardView {

    // MARK: - Actions

    /// Load the provider catalog from the engine. Idempotent — safe to call
    /// from `.task`; subsequent calls are skipped if the catalog already loaded.
    func loadCatalog() async {
        guard catalog.isEmpty, !isCatalogLoading else { return }
        isCatalogLoading = true
        defer { isCatalogLoading = false }
        do {
            catalog = try await appState.providerService.listCatalog()
        } catch {
            // Non-fatal — wizard falls back to its built-in copy.
            errorMessage = "Couldn't load provider list: \(error.localizedDescription)"
        }
    }

    /// Probe Apple Intelligence via the engine route — runs fm-bridge --probe
    /// (availability check only, no model warm-up). The route is also used
    /// by AISettingsView for the "Apple Intelligence not detected" badge.
    func probeAppleIntelligence() async {
        appleProbeState = .probing
        struct Result: Decodable {
            let available: Bool
            let reason: String?
        }
        do {
            let result: Result = try await apiClient.get("/providers/apple-intelligence/probe")
            if result.available {
                appleProbeState = .available
            } else {
                appleProbeState = .unavailable(result.reason ?? "Apple Intelligence isn't available on this Mac.")
            }
        } catch {
            appleProbeState = .unavailable(
                "Couldn't check availability — \(error.localizedDescription). " +
                    "You can still pick this and configure later in Settings."
            )
        }
    }

    /// Hit the local Ollama / LM Studio server with a known endpoint and check
    /// for a 200 response. Endpoint differs per provider:
    ///   - Ollama: GET /api/tags returns a (possibly empty) JSON model list.
    ///   - LM Studio: OpenAI-compatible — GET /v1/models returns the list.
    /// We probe whichever the user picked. Falls back to the catalog default
    /// URL when the user left the field empty (mirrors save behavior).
    func testLocalConnection() async {
        guard let entry = selectedEntry, entry.isLocal else { return }
        let urlString = serverURL.trimmingCharacters(in: .whitespaces).isEmpty
            ? defaultServerURL(for: entry.providerType)
            : serverURL.trimmingCharacters(in: .whitespaces)
        guard let baseURL = URL(string: urlString) else {
            localTestState = .failed("That doesn't look like a URL.")
            return
        }
        var probeURL = baseURL
        switch entry.providerType {
        case "ollama":
            probeURL = baseURL.appendingPathComponent("api/tags")
        case "lmstudio":
            if baseURL.path.hasSuffix("/v1") {
                probeURL = baseURL.appendingPathComponent("models")
            } else {
                probeURL = baseURL.appendingPathComponent("v1/models")
            }
        default:
            // Unknown local server: just hit the base URL.
            break
        }

        localTestState = .testing
        do {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 5
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                localTestState = .failed("Server responded with HTTP \(code).")
                return
            }
            // Distinguish "running but no models installed" from a healthy
            // connection. A reachable server with an empty model list is a
            // different problem than an unreachable one (the catch branch) —
            // the user needs to pull a model, not start the server.
            if probeModelCount(from: data, providerType: entry.providerType) == 0 {
                localTestState = .connected("Connected, but no models are installed yet.")
            } else {
                localTestState = .connected(nil)
            }
        } catch {
            // swiftlint:disable:next line_length
            welcomeLogger.error("Local provider probe failed for \(entry.providerType, privacy: .public) at \(probeURL.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)")
            localTestState = .failed("Couldn't reach \(probeURL.host ?? "server") — is \(entry.name) running?")
        }
    }

    /// Count the models reported by a local provider's list endpoint so the
    /// connection test can tell "running but empty" apart from "running with
    /// models". Ollama (`/api/tags`) returns `{"models":[…]}`; LM Studio and
    /// other OpenAI-compatible servers (`/v1/models`) return `{"data":[…]}`.
    /// Returns `nil` when the shape is unrecognized so callers can treat the
    /// count as unknown (and not falsely warn about missing models).
    func probeModelCount(from data: Data, providerType: String) -> Int? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if providerType == "ollama", let models = json["models"] as? [Any] {
            return models.count
        }
        if let list = json["data"] as? [Any] {
            return list.count
        }
        if let models = json["models"] as? [Any] {
            return models.count
        }
        return nil
    }

    func skipAndDismiss() {
        // Mark complete so the wizard doesn't reappear; user can configure
        // providers anytime in Settings → Models.
        UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
        dismiss()
    }

    func finish() async {
        guard let entry = selectedEntry else { return }
        isSaving = true
        defer { isSaving = false }
        errorMessage = nil

        do {
            // 1. Save the provider config (skip for built-ins — Apple).
            if !entry.isBuiltin {
                let trimmedURL = serverURL.trimmingCharacters(in: .whitespaces)
                let trimmedKey = apiKey.trimmingCharacters(in: .whitespaces)
                _ = try await appState.providerService.createProvider(
                    providerType: entry.providerType,
                    name: entry.name,
                    apiBase: entry.isLocal ? (trimmedURL.isEmpty ? nil : trimmedURL) : nil,
                    apiKey: !entry.isLocal ? (trimmedKey.isEmpty ? nil : trimmedKey) : nil
                )
            }

            // 2. Apply sensible AI defaults so the user doesn't open a fresh
            //    library with empty pickers in every workflow. Same shape
            //    AISettingsView writes (`PUT /api/settings/ai-defaults`).
            //    User can refine in Settings → AI; here we just give them a
            //    working starting point keyed off the provider they picked.
            try? await applyDefaultsForChosenProvider(entry: entry)

            UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")
            dismiss()
        } catch {
            errorMessage = "Couldn't save: \(error.localizedDescription)"
        }
    }

    /// Set the chosen provider as the default for text / vision / transcription.
    /// Uses the provider's catalog `default_model` where available; otherwise
    /// leaves the model field empty so the engine's per-provider fallback kicks
    /// in. Wrapped in `try?` upstream — failure to set defaults shouldn't block
    /// onboarding from completing.
    func applyDefaultsForChosenProvider(entry: Components.Schemas.ProviderCatalogResponse) async throws {
        // Pull current defaults so we don't blow away anything already
        // configured (e.g., if onboarding ran twice).
        var defaults = (try? await appState.fetchAIDefaults()) ?? AIDefaults()

        let providerType = entry.providerType
        let model = entry.defaultModel ?? ""
        let isApple = providerType == "apple"

        // Text — every provider supports text.
        if defaults.textProvider.isEmpty { defaults.textProvider = providerType }
        if defaults.textModel.isEmpty {
            defaults.textModel = isApple ? "apple-intelligence" : model
        }

        // Vision — only set when the provider claims vision support.
        if entry.supportsVision {
            if defaults.visionProvider.isEmpty { defaults.visionProvider = providerType }
            if defaults.visionModel.isEmpty {
                defaults.visionModel = isApple ? "apple-vision" : model
            }
        }

        // Audio (transcription) — leave the engine's fallback to handle this
        // for providers without dedicated audio models. Setting the provider
        // here only when we know it'll work would mean a per-provider table;
        // safer to let user pick in Settings → AI → Audio if they care.
        if isApple {
            if defaults.audioProvider.isEmpty { defaults.audioProvider = providerType }
            if defaults.audioModel.isEmpty { defaults.audioModel = "apple-speech" }
            if defaults.smallProvider.isEmpty { defaults.smallProvider = providerType }
            if defaults.smallModel.isEmpty { defaults.smallModel = "apple-intelligence" }
            if defaults.largeProvider.isEmpty { defaults.largeProvider = providerType }
            if defaults.largeModel.isEmpty { defaults.largeModel = "apple-intelligence" }
        }

        try await appState.saveAIDefaults(defaults)
    }
}
