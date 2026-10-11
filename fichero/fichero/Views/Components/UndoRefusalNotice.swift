import SwiftUI

/// The engine's sentence when it would not take a step back (`undo.refusal`, #5658), shown in the
/// window that asked: "This note was changed in another window at 14:02. Your delete was not
/// undone." Nothing changed; a `changed` step is still on the window's stack, an `already-undone`
/// or `gone` one is not. It stays until dismissed or for a little while, so a person can read it.
struct UndoRefusalNotice: View {
    let steps: WindowSteps

    var body: some View {
        if let sentence = steps.refusal {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Image(systemName: "arrow.uturn.backward.circle")
                    .foregroundStyle(.orange)
                Text(sentence)
                    .fixedSize(horizontal: false, vertical: true)
                Button("OK") { steps.refusal = nil }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: 520)
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 12))
            .padding(.bottom, 16)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("undo.refusal.notice")
            .task(id: sentence) {
                try? await Task.sleep(for: .seconds(12))
                if steps.refusal == sentence { steps.refusal = nil }
            }
        }
    }
}

#Preview("Undo refused") {
    let steps = WindowSteps()
    steps.refusal = "This note was changed in another window at 14:02. Your delete was not undone."
    return UndoRefusalNotice(steps: steps)
        .frame(width: 600, height: 120, alignment: .bottom)
}
