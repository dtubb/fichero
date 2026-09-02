import SwiftUI

extension ImageEditorView {
    /// Copy / Paste EDITS — Lightroom's Copy & Paste Settings, on the recipe
    /// rather than the pixels (Daniel, 2026-09-02).
    ///
    /// It sits on its own menu instead of ⌘C / ⌘V because those chords already
    /// mean "copy the picture" over an image, and a surface where the same
    /// chord means two things depending on which pane has focus is exactly the
    /// ambiguity the visible-surface selection ruling exists to prevent.
    var editsClipboardMenu: some View {
        Menu {
            Button {
                model.copyEdits()
            } label: {
                Label(
                    model.chain.isEmpty
                        ? "Copy Edits (no steps)"
                        : "Copy Edits (\(model.chain.operations.count) steps)",
                    systemImage: "doc.on.doc"
                )
            }
            .disabled(model.isBusy || model.chain.isEmpty)
            .accessibilityIdentifier("imageEditCopyEdits")

            Button {
                Task { await model.pasteEdits() }
            } label: {
                Label(pasteTitle, systemImage: "doc.on.clipboard")
            }
            .disabled(model.isBusy || ImageEditClipboard.shared.isEmpty)
            .accessibilityIdentifier("imageEditPasteEdits")

            if selectedEditableDocs.count > 1 {
                Divider()
                Button {
                    showPasteManyConfirm = true
                } label: {
                    Label(
                        "Paste Edits to \(selectedEditableDocs.count) Selected",
                        systemImage: "square.stack.3d.up"
                    )
                }
                .disabled(model.isBusy || ImageEditClipboard.shared.isEmpty)
                .accessibilityIdentifier("imageEditPasteEditsToSelection")
            }
        } label: {
            Image(systemName: "doc.on.doc")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("Copy this image's edit steps, or paste copied steps onto this image")
        .accessibilityLabel("Copy or paste edit steps")
        .accessibilityIdentifier("imageEditClipboardMenu")
        // Pasting REPLACES each target's chain, so a paste across a selection
        // can discard saved work on files that are not even on screen. That
        // gets a confirmation; the single-image paste does not, because the
        // one image whose edits it replaces is the one you are looking at and
        // Undo/Revert are right there.
        .confirmationDialog(
            "Paste edits onto \(selectedEditableDocs.count) selected files?",
            isPresented: $showPasteManyConfirm,
            titleVisibility: .visible
        ) {
            Button("Paste Edits", role: .destructive) {
                Task { await model.pasteEdits(to: selectedEditableDocs.map(\.id)) }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(pasteManyMessage)
        }
    }

    private var pasteManyMessage: String {
        let steps = ImageEditClipboard.shared.count
        return "Each file's own edit steps are replaced by the \(steps) copied step(s). "
            + "Original files are never changed."
    }

    /// Menu wording for Paste, naming what is on the clipboard so the user is
    /// not asked to remember what they copied three images ago.
    private var pasteTitle: String {
        let clipboard = ImageEditClipboard.shared
        if clipboard.isEmpty { return "Paste Edits (nothing copied)" }
        return "Paste Edits (\(clipboard.count) steps)"
    }
}
