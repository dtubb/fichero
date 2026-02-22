import SwiftUI
import FicheroAPIClient

// MARK: - Step 1: Choose Provider

extension AddProviderSheet {
    var chooseProviderView: some View {
        VStack(spacing: 0) {
            // Title
            Text("Choose a provider...")
                .font(.title2)
                .fontWeight(.medium)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 8)

            // First launch explanation
            if isFirstLaunch {
                Text("Select an AI provider to enable transcription, chat, and other AI features.")
                    .font(.callout)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 12)
            }

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Radio button list (Apple Mail style) - only show providers not yet added
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if availableCatalog.isEmpty {
                            Text("All providers have been added")
                                .foregroundColor(.secondary)
                                .padding(.vertical, 40)
                        } else {
                            ForEach(availableCatalog) { entry in
                                ProviderRadioRow(
                                    entry: entry,
                                    isSelected: selectedType == entry.providerType
                                ) {
                                    selectedType = entry.providerType
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 8)
                }
            }

            Divider()

            // Footer with buttons
            HStack {
                // Help button
                Button {
                    // help action
                } label: {
                    Image(systemName: "questionmark.circle")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)

                Spacer()

                Button("Cancel") {
                    if !isFirstLaunch {
                        dismiss()
                    }
                }
                .keyboardShortcut(.cancelAction)
                .disabled(isFirstLaunch && catalog.isEmpty)

                Button(selectedEntry?.isBuiltin == true ? "Add" : "Continue") {
                    let providerType = selectedEntry?.providerType ?? "nil"
                    let isBuiltin = selectedEntry?.isBuiltin ?? false
                    addProviderLogger.info("Button tapped, selectedEntry=\(providerType), isBuiltin=\(isBuiltin)")
                    // For built-in providers, add directly without config step
                    if let entry = selectedEntry, entry.isBuiltin {
                        addProviderLogger.info("isBuiltin=true, calling addProvider()")
                        addProvider()
                    } else {
                        addProviderLogger.info("isBuiltin=false, going to step 2")
                        step = 2
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(selectedType == nil)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
    }
}
