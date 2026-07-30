import SwiftUI

// MARK: - ReaderToolbar control sections

extension ReaderToolbar {
    // MARK: - Chrome (close + title)

    private func closePane() {
        if let actions = splitAxisActions, actions.hasVertical || actions.hasHorizontal {
            actions.onCollapseSplit()
            return
        }
        onClose?()
    }

    @ViewBuilder
    var chromeSection: some View {
        if onClose != nil || isInSplit {
            Button {
                closePane()
            } label: {
                Image(systemName: ToolbarSymbols.closePane)
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help(isInSplit ? "Close this split" : "Close this pane")
            .accessibilityLabel(isInSplit ? "Close this split" : "Close this pane")

            sectionDivider
        }

        if let title, !title.isEmpty {
            Image(systemName: "doc.richtext")
                .imageScale(.small)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            sectionDivider
        }
    }

    // MARK: - Page navigation

    @ViewBuilder
    var pageNavSection: some View {
        let enabled = (pageNav?.pageCount ?? 0) > 1
        let indexLabel = pageNav.map { "\($0.pageIndex + 1) / \($0.pageCount)" } ?? "– / –"

        Button {
            pageNav?.goPrevious()
        } label: {
            Image(systemName: "chevron.left")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .disabled(!(enabled && (pageNav?.canGoPrevious ?? false)))
        .help("Previous Page")
        .accessibilityLabel("Previous Page")
        .accessibilityIdentifier("pdfPreviousPage")

        Text(indexLabel)
            .font(.caption)
            .monospacedDigit()
            .foregroundStyle(.secondary)
            .frame(minWidth: 48)

        Button {
            pageNav?.goNext()
        } label: {
            Image(systemName: "chevron.right")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .disabled(!(enabled && (pageNav?.canGoNext ?? false)))
        .help("Next Page")
        .accessibilityLabel("Next Page")
        .accessibilityIdentifier("pdfNextPage")

        sectionDivider
    }

    // MARK: - Zoom

    @ViewBuilder
    var zoomSection: some View {
        Button(action: zoomOut) {
            Image(systemName: "minus.magnifyingglass")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Zoom Out")
        .accessibilityLabel("Zoom Out")

        Text("\(scalePercent)%")
            .font(.caption)
            .monospacedDigit()
            .frame(width: 50)

        Button(action: zoomIn) {
            Image(systemName: "plus.magnifyingglass")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Zoom In")
        .accessibilityLabel("Zoom In")

        sectionDivider
    }

    @ViewBuilder
    var fitSection: some View {
        Button(action: fitToWindow) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Fit to Window")
        .accessibilityLabel("Fit to Window")

        Button(action: actualSize) {
            Image(systemName: "1.square")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Actual Size (100%)")
        .accessibilityLabel("Actual Size (100%)")

        sectionDivider
    }

    // MARK: - Magnifier panel

    @ViewBuilder
    var magnifierButton: some View {
        let binding = magnifierEnabled ?? .constant(false)
        Button {
            binding.wrappedValue.toggle()
        } label: {
            Image(systemName: "rectangle.bottomhalf.inset.filled")
        }
        .buttonStyle(.plain)
        .foregroundColor(binding.wrappedValue ? .accentColor : .primary)
        .disabled(magnifierEnabled == nil)
        .help(magnifierEnabled == nil ? "Magnifier panel (not available for this document)" : "Magnifier Panel")
        .accessibilityLabel("Magnifier Panel")
    }

    // MARK: - Loupe

    @ViewBuilder
    var loupeSection: some View {
        let enabledBinding = loupeEnabled ?? .constant(false)
        let lockedBinding = loupeLocked ?? .constant(false)

        HStack(spacing: 4) {
            Button {
                enabledBinding.wrappedValue.toggle()
            } label: {
                Image(systemName: enabledBinding.wrappedValue
                        ? "magnifyingglass.circle.fill"
                        : "magnifyingglass.circle")
            }
            .buttonStyle(.plain)
            .foregroundColor(enabledBinding.wrappedValue ? .accentColor : .primary)
            .disabled(loupeEnabled == nil)
            .help(loupeEnabled == nil ? "Loupe (not available for this document)" : "Toggle loupe")
            .accessibilityLabel("Loupe")

            if loupeEnabled != nil, enabledBinding.wrappedValue {
                Button {
                    lockedBinding.wrappedValue.toggle()
                } label: {
                    Image(systemName: lockedBinding.wrappedValue ? "lock.fill" : "lock.open")
                }
                .buttonStyle(.plain)
                .foregroundColor(lockedBinding.wrappedValue ? .accentColor : .secondary)
                .help(lockedBinding.wrappedValue ? "Unlock loupe" : "Lock loupe")
                .accessibilityLabel(lockedBinding.wrappedValue ? "Unlock loupe" : "Lock loupe")

                if let mag = loupeMagnification {
                    Text(String(format: "%.1fx", mag.wrappedValue))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundColor(.secondary)
                        .frame(width: 32)

                    Slider(value: mag, in: 1...8, step: 0.5)
                        .frame(width: 80)
                }
            }
        }

        sectionDivider
    }

    // MARK: - Image editing

    @ViewBuilder
    var editButton: some View {
        let binding = isEditing ?? .constant(false)
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                binding.wrappedValue.toggle()
            }
        } label: {
            Image(systemName: binding.wrappedValue ? "pencil.circle.fill" : "pencil.circle")
        }
        .buttonStyle(.plain)
        .foregroundColor(binding.wrappedValue ? .accentColor : .primary)
        .disabled(isEditing == nil)
                .help(isEditing == nil
                ? "Image editing (not available for this document)"
                : (binding.wrappedValue
                    ? "Done — return to viewing"
                    : "Edit image (crop, rotate, straighten, enhance, remove background)"))
        .accessibilityLabel(binding.wrappedValue ? "Done editing" : "Edit image")
        .accessibilityIdentifier("canvasEditModeToggle")

        sectionDivider
    }

    // MARK: - Annotation

    @ViewBuilder
    var annotationSection: some View {
        ForEach(ReaderAnnotationTool.allCases) { tool in
            Button {
                onAnnotate?(tool)
            } label: {
                Image(systemName: tool.icon)
            }
            .buttonStyle(.plain)
            .disabled(onAnnotate == nil)
            .help(onAnnotate == nil ? "\(tool.label) (not available for this document)" : tool.label)
            .accessibilityLabel(tool.label)
            .accessibilityIdentifier("readerAnnotate_\(tool.rawValue)")
        }
    }

    // MARK: - Pin (trailing, after split buttons)

    @ViewBuilder
    var pinButton: some View {
        if let isPinned, let onTogglePin {
            sectionDivider

            Button(action: onTogglePin) {
                Image(systemName: isPinned.wrappedValue ? "pin.fill" : "pin")
                    .font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .foregroundStyle(isPinned.wrappedValue ? Color.accentColor : Color.secondary)
            .help(isPinned.wrappedValue ? "Unpin — follow current selection" : "Pin to this document")
            .accessibilityLabel(isPinned.wrappedValue ? "Unpin" : "Pin to this document")
        }
    }
}
