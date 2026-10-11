import FicheroAPIClient
import SwiftUI

/// What Fichero runs (section 7d, ruled 2026-10-11, #5668; `source.onboard.app.what-fichero-runs`): what Fichero can
/// do, and with what, then the two accounts it suggests, taken right here. It replaces "AI is optional".
enum WhatFicheroRuns {
    static let title = "What Fichero runs"
    static let subtitle = "Fichero runs these on your Mac where it can; remote models are optional."

    /// What Fichero can do, and with what.
    static let rows: [(work: String, with: String)] = [
        ("Reading pages", "Kraken, Apple Vision, MLX vision models"),
        ("Finding regions and lines", "YOLO, Kraken"),
        ("Names and statements", "spaCy"),
        ("Speech", "Whisper"),
        ("Remote models", "OpenRouter, Anthropic, OpenAI, Google")
    ]

    /// The two accounts it suggests, by the engine's provider type, each with what it is for.
    struct Account: Equatable {
        let providerType: String
        let title: String
        let purpose: String
        let keyPrompt: String
    }

    static let accounts: [Account] = [
        Account(providerType: "huggingface", title: "Hugging Face",
                purpose: "Finds and downloads the models a step needs.", keyPrompt: "Access token (hf_…)"),
        Account(providerType: "openrouter", title: "OpenRouter",
                purpose: "Remote readers and models, when you allow pages to leave this Mac.", keyPrompt: "API key (sk-or-…)")
    ]
}

struct WhatFicheroRunsFields: View {
    let providers: ProviderAPIService
    /// Choose a Provider: opens the provider sheet in this step (`source.onboard.app.provider-sheet-in-step`).
    let chooseProvider: () -> Void
    let onAccountAdded: () async -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
                ForEach(WhatFicheroRuns.rows, id: \.work) { row in
                    GridRow {
                        Text(row.work).font(.callout.weight(.medium))
                        Text(row.with).font(.callout).foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            ForEach(WhatFicheroRuns.accounts, id: \.providerType) { account in
                WhatFicheroRunsAccountRow(account: account, providers: providers, onAdded: onAccountAdded)
            }
            Button("Choose a Provider…", action: chooseProvider)
                .buttonStyle(.bordered)
                .help("Anthropic, OpenAI, Google, or a model on this Mac")
        }
    }
}

/// One suggested account: its key typed here and added as a provider (`POST /api/providers`).
struct WhatFicheroRunsAccountRow: View {
    let account: WhatFicheroRuns.Account
    let providers: ProviderAPIService
    let onAdded: () async -> Void

    @State private var key = ""
    @State private var isAdding = false
    @State private var added = false
    @State private var refusal: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(account.title).font(.callout.weight(.medium))
                Text(account.purpose).font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                SecureField(account.keyPrompt, text: $key)
                    .textFieldStyle(.roundedBorder)
                    .disabled(added)
                if added {
                    Label("Added", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                } else {
                    Button("Add") { add() }
                        .disabled(key.trimmingCharacters(in: .whitespaces).isEmpty || isAdding)
                }
            }
            if let refusal {
                Text(refusal).font(.caption).foregroundStyle(.orange)
            }
        }
    }

    private func add() {
        isAdding = true
        Task {
            defer { isAdding = false }
            do {
                _ = try await providers.createProvider(
                    providerType: account.providerType, apiKey: key.trimmingCharacters(in: .whitespaces)
                )
                added = true
                refusal = nil
                await onAdded()
            } catch {
                refusal = "Could not add the \(account.title) account: \(error.localizedDescription)"
            }
        }
    }
}

#Preview("What Fichero runs") {
    WhatFicheroRunsFields(
        providers: ProviderAPIService(ficheroClient: FicheroClient(libraryPath: nil)),
        chooseProvider: {},
        onAccountAdded: {}
    )
    .padding()
    .frame(width: 560)
}
