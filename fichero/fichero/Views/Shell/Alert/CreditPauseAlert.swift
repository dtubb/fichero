import SwiftUI

/// Mounts the one box of a run paused for its provider's credit (`recipes-run.credit.out-of-credit-pauses-and-asks`, #6675):
/// the store builds it (`ActivityStore.askAboutCredit`), this shows it. Optional store: a host that does not inherit the
/// window's environment shows nothing rather than trapping.
struct CreditPauseAlert: ViewModifier {
    @Environment(ActivityStore.self) private var store: ActivityStore?
    @Environment(\.openURL) private var openURL

    func body(content: Content) -> some View {
        if let store {
            content.failureAlert(Bindable(store).creditPause)
                .onAppear { store.openProviderPage = { openURL($0) } }
        } else {
            content
        }
    }
}
