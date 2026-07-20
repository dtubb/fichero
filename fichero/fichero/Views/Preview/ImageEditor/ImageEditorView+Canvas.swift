#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

extension ImageEditorView {
    // MARK: - Canvas

    var canvas: some View {
        ZStack {
            CheckerboardPattern().opacity(0.12)
            if compareMode == .sideBySide {
                if let original = model.originalPreview, let edited = model.editedPreview {
                    HStack(spacing: 8) {
                        comparePane(image: original.image, pixelSize: original.pixelSize, title: "Original")
                        comparePane(image: edited.image, pixelSize: edited.pixelSize, title: "Edited")
                    }
                    .padding(8)
                } else {
                    ProgressView("Loading compare preview…")
                        .controlSize(.small)
                }
            } else if compareMode == .wipe {
                if let original = model.originalPreview, let edited = model.editedPreview {
                    GeometryReader { geo in
                        let fitted = ImageFit.fittedRect(
                            imagePixelSize: edited.pixelSize,
                            in: CGSize(width: geo.size.width - 24, height: geo.size.height - 24)
                        )
                        let frame = fitted.offsetBy(dx: 12, dy: 12)
                        let split = max(0, min(1, compareSplit))
                        ZStack(alignment: .topLeading) {
                            // Edited underneath — full size (revealed on the right).
                            Image(platformImage: edited.image)
                                .resizable()
                                .interpolation(.high)
                                .aspectRatio(contentMode: .fit)
                                .frame(width: frame.width, height: frame.height)
                            // Original on top — clipped to the left split portion,
                            // so left = Before (original), right = After (edited)
                            // and the labels below read correctly (#1538).
                            Image(platformImage: original.image)
                                .resizable()
                                .interpolation(.high)
                                .aspectRatio(contentMode: .fit)
                                .frame(width: frame.width, height: frame.height)
                                .frame(width: split * frame.width, height: frame.height, alignment: .leading)
                                .clipped()
                            // Divider line
                            Rectangle()
                                .fill(Color.white.opacity(0.9))
                                .frame(width: 2, height: frame.height)
                                .offset(x: split * frame.width - 1)
                            // Before / After labels
                            HStack(spacing: 0) {
                                Text("Before")
                                    .font(.caption2.weight(.medium))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(Color.black.opacity(0.45))
                                    .foregroundStyle(.white)
                                    .cornerRadius(3)
                                    .padding(.leading, 6).padding(.top, 6)
                                    .opacity(split > 0.1 ? 1 : 0)
                                Spacer()
                                Text("After")
                                    .font(.caption2.weight(.medium))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(Color.black.opacity(0.45))
                                    .foregroundStyle(.white)
                                    .cornerRadius(3)
                                    .padding(.trailing, 6).padding(.top, 6)
                                    .opacity(split < 0.9 ? 1 : 0)
                            }
                            .frame(width: frame.width)
                            // Drag handle on divider
                            Image(systemName: "arrow.left.and.right")
                                .font(.caption2)
                                .padding(5)
                                .background(Color.white.opacity(0.88))
                                .clipShape(Circle())
                                .offset(x: split * frame.width - 11, y: frame.height / 2 - 11)
                        }
                        .frame(width: frame.width, height: frame.height)
                        .offset(x: frame.minX, y: frame.minY)
                        // Drag on the image to adjust the wipe position
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    compareSplit = max(0, min(1, value.location.x / frame.width))
                                }
                        )
                    }
                } else {
                    ProgressView("Loading compare preview…")
                        .controlSize(.small)
                }
            } else {
                // Single-mode: DocumentCanvas gives zoom/loupe/magnifier (#1402).
                if let rendered = model.preview?.image {
                    DocumentCanvas(
                        content: .imageRendered(
                            image: rendered,
                            documentId: activeDocumentID
                        )
                    )
                } else {
                    // No rendered frame yet — entering edit clears `preview` and
                    // then awaits the (heavier) apply_edits render, so driving the
                    // canvas with a nil rendered image left it blank/black on enter
                    // (#3593). Fall back to the known-good source display image (the
                    // exact canvas view mode already uses) so the pane shows the
                    // picture immediately and swaps to the edited frame once it lands.
                    DocumentCanvas(
                        content: .imageStorageDisplay(documentId: activeDocument.id)
                    )
                }
            }

            // Busy overlay for any in-flight edit/load, in every compare mode
            // (#1532). Translucent so the last image stays visible mid-op; the
            // labelled spinner makes clear a potentially-slow op (remove-bg,
            // despeckle, enhance) is actually running.
            if model.isBusy {
                Color.black.opacity(0.10).allowsHitTesting(false)
                ProgressView("Working…")
                    .controlSize(.small)
                    .padding(10)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
                    .allowsHitTesting(false)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .textBackgroundColor))
    }

    private func comparePane(image: PlatformImage, pixelSize: CGSize, title: String) -> some View {
        VStack(spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            GeometryReader { geo in
                let fitted = ImageFit.fittedRect(
                    imagePixelSize: pixelSize,
                    in: CGSize(width: geo.size.width - 12, height: geo.size.height - 12)
                )
                let frame = fitted.offsetBy(dx: 6, dy: 6)
                Image(platformImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
