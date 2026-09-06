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
                // A help button used to sit here with an empty action -- it
                // drew a "?" and did nothing when clicked. Labelling it for
                // VoiceOver would have announced "Help" for a control that
                // offers none, which is worse than the silence it replaced.
                // Removed rather than pointed somewhere invented; wire a real
                // help target back in when there is one to point at.
                Spacer()

                Button("Cancel") {
                    if !isFirstLaunch {
                        dismiss()
                    }
                }
                .keyboardShortcut(.cancelAction)
                .disabled(isFirstLaunch && catalog.isEmpty)

                Button(addsDirectly(selectedEntry) ? "Add" : "Continue") {
                    let providerType = selectedEntry?.providerType ?? "nil"
                    addProviderLogger.info("Button tapped, selectedEntry=\(providerType)")
                    // Built-in AND managed-local runtimes (MLX/spaCy/Kraken/
                    // Whisper) add directly — they need no Server URL or API key;
                    // their setup lives in the provider row. Only genuinely
                    // external providers go to the configure step.
                    if let entry = selectedEntry, addsDirectly(entry) {
                        addProviderLogger.info("adds directly, calling addProvider()")
                        addProvider()
                    } else {
                        addProviderLogger.info("needs config, going to step 2")
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
