import FicheroAPIClient
import SwiftUI

// MARK: - Step 2: Configure Provider

extension AddProviderSheet {
    var configureProviderView: some View {
        VStack(spacing: 0) {
            // Header with provider info
            HStack(spacing: 12) {
                if let entry = selectedEntry {
                    ProviderLogoView(entry: entry, size: 40)
                }

                VStack(alignment: .leading) {
                    Text(selectedEntry?.name ?? "Provider")
                        .font(.title2)
                        .fontWeight(.medium)
                    Text(selectedEntry?.description ?? "")
                        .font(.callout)
                        .foregroundColor(.secondary)
                }

                Spacer()
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()

            // Configuration form
            VStack(alignment: .leading, spacing: 16) {
                if let entry = selectedEntry {
                    if entry.isLocal && !entry.isBuiltin {
                        // Local servers (not built-in): optional server URL
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Server URL (optional)")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            TextField(defaultServerUrl(for: entry.providerType), text: $serverUrl)
                                .textFieldStyle(.roundedBorder)

                            Text("Leave empty to use default: \(defaultServerUrl(for: entry.providerType))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        if entry.providerType == "omlx" {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("API Key (optional)")
                                    .font(.subheadline)
                                    .fontWeight(.medium)

                                SecureField("Any local key", text: $apiKey)
                                    .textFieldStyle(.roundedBorder)

                                Text("oMLX accepts an arbitrary local key; it does not need an OpenAI sk- key.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    } else if !entry.isLocal {
                        // Cloud providers: API key optional (can add later)
                        VStack(alignment: .leading, spacing: 6) {
                            Text("API Key (optional)")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            SecureField("Enter your API key", text: $apiKey)
                                .textFieldStyle(.roundedBorder)

                            Text("You can add the API key later from Providers settings.")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            if let url = entry.apiKeyUrl {
                                Link("Get an API key from \(entry.name)", destination: URL(string: url)!)
                                    .font(.caption)
                            }
                        }
                    }
                    // Note: Built-in providers (isBuiltin=true) should never reach step 2
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Spacer()

            Divider()

            // Footer with buttons
            HStack {
                Button("Back") {
                    step = 1
                }

                Spacer()

                Button("Add") {
                    addProviderLogger.info("Step 2 Add button tapped")
                    addProvider()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isAdding)  // Allow adding without API key - can configure later
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }
}
