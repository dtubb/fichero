import Foundation

/// What the Enhance popover asks for before a person touches it (`image.enhance.editor-enhance-is-the-new-step`):
/// the ported local-contrast cleanup, handwritten profile. The plain brightness/contrast/sharpness sliders stay one switch away.
struct EnhanceChoice: Equatable {
    var localContrast = true
    var typescript = false

    var method: String { localContrast ? "clahe" : "pil" }
    var profile: String { typescript ? "typescript" : "handwritten" }
}
