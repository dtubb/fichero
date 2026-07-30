import SwiftUI

extension ImmersiveReaderView {
    var controlsOverlay: some View {
        VStack {
            HStack {
                // Source (page image) / Diplomatic (page_content) / one per
                // translated language (#3325 reader slice, #3329). Dynamic, so a
                // Menu rather than a fixed segmented control.
                Menu {
                    Button { representationKey = "source" } label: {
                        Label("Source", systemImage: "photo")
                    }
                    Button { representationKey = "diplomatic" } label: {
                        Label("Diplomatic", systemImage: "text.alignleft")
                    }
                    if !translations.isEmpty {
                        Divider()
                        Section("Translations") {
                            ForEach(translations) { translation in
                                Button(translation.displayName) {
                                    representationKey = "lang:\(translation.lang)"
                                }
                            }
                        }
                    }
                    // Model-generated renditions of this page (#4329) —
                    // Markdown / HTML / SVG, rendered in place.
                    if !renditions.isEmpty {
                        Divider()
                        Section("Renditions") {
                            ForEach(renditions) { rendition in
                                Button(Self.renditionTitle(forFormat: renditionFormat(rendition))) {
                                    representationKey = "rendition:\(rendition.id)"
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "character.book.closed")
                        Text(currentRepresentationLabel)
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.ultraThinMaterial, in: Capsule())
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Switch the reader between the page image, transcript, and translations")

                provenanceCaption

                Spacer()
                Button(action: exit) {
                    Image(systemName: "xmark")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(10)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Exit full screen reader")
                .keyboardShortcut(.cancelAction)
                .help("Exit full screen (Esc)")
            }
            .padding(16)

            Spacer()

            // Bottom control bar — page navigation + title. Auto-hides with the
            // rest of the chrome. A thumbnail filmstrip + annotation palette
            // graft on here next (#2516).
            HStack(spacing: 16) {
                Button {
                    navigate(by: -1)
                } label: {
                    Image(systemName: "chevron.left")
                }
                .disabled(siblingIndex == nil || siblingIndex == 0)
                .accessibilityLabel("Previous page")

                Text(document.name)
                    .font(.callout)
                    .foregroundStyle(.white)
                    .lineLimit(1)

                Button {
                    navigate(by: 1)
                } label: {
                    Image(systemName: "chevron.right")
                }
                .disabled(siblingIndex == nil || siblingIndex == siblings.count - 1)
                .accessibilityLabel("Next page")

                // Reading-mark palette (#2516 / #3548): star + bookmark the
                // current page without leaving full screen.
                Divider().frame(height: 16).overlay(Color.white.opacity(0.3))

                Button {
                    markCurrentPage(kind: .rating, label: "Starred")
                } label: {
                    Image(systemName: "star")
                }
                .disabled(annotationStore == nil)
                .accessibilityLabel("Star this page")
                .help("Star this page as a reading mark")

                Button {
                    markCurrentPage(kind: .bookmark, label: "Bookmarked")
                } label: {
                    Image(systemName: "bookmark")
                }
                .disabled(annotationStore == nil)
                .accessibilityLabel("Bookmark this page")
                .help("Bookmark this page")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(.bottom, 24)
        }
    }
}
