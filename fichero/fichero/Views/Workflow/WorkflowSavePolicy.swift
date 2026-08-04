/// Whether the editor may persist a workflow (#4514).
///
/// Locked system presets (Default Workflows) are read-only by design — the
/// server 403s every write — so no save path may even fire the request for
/// them. Checks BOTH the editor's copy and the canonical sidebar row: a stale
/// editor snapshot that lost the flag must not sneak a doomed PUT through.
enum WorkflowSavePolicy {
    static func canAutoSave(editorIsSystem: Bool, canonicalIsSystem: Bool?) -> Bool {
        !editorIsSystem && canonicalIsSystem != true
    }
}


