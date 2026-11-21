#if os(iOS) || os(visionOS)
import SwiftUI

/// The picture at the top of the Connect screen's QR section: the engine and a viewfinder, or "Connecting…" while pairing.
struct ConnectQRCard: View {
    let isPairing: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 22)
                .fill(Color.accentColor.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 22)
                        .stroke(Color.accentColor.opacity(0.18), lineWidth: 1)
                )
            if isPairing {
                ProgressView("Connecting…")
            } else {
                VStack(spacing: 14) {
                    Image("Engine")
                        .resizable()
                        .interpolation(.high)
                        .scaledToFit()
                        .frame(width: 112, height: 112)
                        .accessibilityHidden(true)

                    Image(systemName: "qrcode.viewfinder")
                        .font(.system(size: 34))
                        .foregroundStyle(Color.accentColor)
                        .accessibilityHidden(true)
                }
            }
        }
        .frame(height: 220)
        .listRowInsets(EdgeInsets(top: 18, leading: 18, bottom: 14, trailing: 18))
    }
}
#endif
