import SwiftUI

/// The alert for a `FailureAlertPrompt` (`run.fail.alert-on-a-failed-run`, #6354): its title, its message, a button for each fix and
/// a dismiss button. It is generic: it knows nothing of runs or pairings. Mount it where the prompt lives, with
/// `.failureAlert($prompt)`; setting the prompt to nil, or pressing any button, closes it.
struct FailureAlert: ViewModifier {
    @Binding var prompt: FailureAlertPrompt?

    func body(content: Content) -> some View {
        content.alert(
            prompt?.title ?? "",
            isPresented: Binding(get: { prompt != nil }, set: { if !$0 { prompt = nil } }),
            presenting: prompt
        ) { shown in
            ForEach(shown.fixes) { fix in
                Button(fix.label) { fix.action() }
            }
            Button(shown.dismissLabel, role: .cancel) {}
        } message: { shown in
            Text(shown.message)
        }
    }
}

extension View {
    /// Shows `prompt` as a failure alert while it is not nil.
    func failureAlert(_ prompt: Binding<FailureAlertPrompt?>) -> some View {
        modifier(FailureAlert(prompt: prompt))
    }
}

#Preview("A failure with a fix") {
    @Previewable @State var prompt: FailureAlertPrompt? = FailureAlertPrompt(
        title: "Could not pair",
        message: FailureAlertPrompt.message(why: "The other Mac did not answer.", fix: "Check it is awake and on the same network."),
        fixes: [.init(id: 0, label: "Try Again", action: {})])
    Text("Behind the alert").frame(width: 480, height: 240).failureAlert($prompt)
}
