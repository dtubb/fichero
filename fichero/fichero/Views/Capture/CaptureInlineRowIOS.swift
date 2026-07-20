#if os(iOS) || os(tvOS) || os(visionOS)
import SwiftUI
import UIKit

// Promoted private → internal: constructed by `RemoteConnectionSetupView`
// (IOSPairingViews.swift) after this type was split out of FicheroApp_iOS.swift
// for file_length.
struct InlineCaptureRow: View {
    let item: MobileCaptureQueueItem
    @Bindable var queue: MobileCaptureQueueStore

    var body: some View {
        HStack(spacing: 12) {
            thumbnailView
            Text(item.catalog.documentName(fallback: item.imageFileName))
                .font(.body.weight(.semibold))
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }

    private var thumbnailView: some View {
        Group {
            if let image = UIImage(contentsOfFile: queue.imageURL(for: item).path) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    Color.accentColor.opacity(0.12)
                    Image(systemName: "photo")
                        .foregroundStyle(Color.accentColor)
                }
            }
        }
        .frame(width: 42, height: 42)
        .clipShape(RoundedRectangle(cornerRadius: 11))
    }
}
#endif
