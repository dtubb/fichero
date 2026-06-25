import FicheroAPIClient
import SwiftUI

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
                Text("Pick the cheapest provider that still works for your tasks. You can add stronger models later in Settings.")
                    .font(.callout)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 12)
            }

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if availableCatalog.isEmpty {
                Text("All providers have been added")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(availableCatalog) { entry in
                    ProviderRadioRow(
                        entry: entry,
                        isSelected: selectedType == entry.providerType
                    ) {
                        selectedType = entry.providerType
                    }
                    .listRowInsets(EdgeInsets(top: 0, leading: 24, bottom: 0, trailing: 24))
                }
                .listStyle(.plain)
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
