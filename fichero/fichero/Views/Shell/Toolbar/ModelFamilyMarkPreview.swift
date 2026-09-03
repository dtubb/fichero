import SwiftUI

// Temporary verification preview for the "giant model icon" bug (Daniel,
// 2026-09-03): renders ModelFamilyMark in BOTH real contexts — the toolbar
// chip (side 16) and the chain-rail Menu lozenge (side 12) — beside the SF
// symbols they must match. Delete after the fix is confirmed in a build.
#Preview("Model marks in context") {
    VStack(alignment: .leading, spacing: 16) {
        // Toolbar-chip context: mark between two .body SF-symbol neighbours.
        HStack(spacing: 10) {
            Image(systemName: "sidebar.left").font(.body)
            ModelFamilyMark(model: "gemini-2.5-flash", provider: "google", side: 16)
            ModelFamilyMark(model: "claude-sonnet-5", provider: "openrouter", side: 16)
            ModelFamilyMark(model: "apple-fm", provider: "apple", side: 16)
            ModelFamilyMark(model: "mystery-model", provider: "unknown", side: 16)
            Image(systemName: "play.circle").font(.body)
        }

        Divider()

        // Chain-rail context: the EXACT structure of the workflow sentence's
        // model token — Menu + Label + ChainTokenLabelStyle + side-12 mark.
        HStack(spacing: 6) {
            Text("run with").font(WorkflowBar.chainConnectiveFont)
            Menu {
                Button("Pick a model") {}
            } label: {
                Label {
                    Text("gemini-2.5-flash").font(WorkflowBar.chainTokenFont)
                } icon: {
                    ModelFamilyMark(model: "gemini-2.5-flash", provider: "google", side: 12)
                }
            }
            .labelStyle(ChainTokenLabelStyle())
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            Text("on 3 documents").font(WorkflowBar.chainConnectiveFont)
        }
    }
    .padding(24)
}
