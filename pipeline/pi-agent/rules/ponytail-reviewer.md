# Ponytail review lens — one named check in every review

Copied from the ponytail plugin's `ponytail-review` skill (4.6.0, MIT) for the pipeline's reviewer. This is ONE of
the reviewer's named checks; correctness, regressions, the spec diff and security are the others.

Hunt complexity only. For every finding, one line: location, what to cut, what replaces it.

Look for: reinvented standard library; an unneeded dependency; a speculative abstraction (an interface with one
implementation, a factory for one product, config for a constant); dead flexibility (a parameter nothing passes, a
branch nothing reaches); scaffolding "for later"; a longer explanation than the code it defends.

Never flag: a single smoke test or an assert-based self-check (the ponytail minimum); validation at a trust
boundary; error handling that prevents data loss; a `ponytail:` comment naming a ceiling (that is intent, not debt).

Pattern: `L30-44: shrink: manual loop builds dict. dict(zip(keys, values)), 1 line.`

End with the only metric that matters: `net: -<N> lines possible.` If there is nothing to cut: `Lean already. Ship.`

Your verdict goes through the `verdict` tool: `verdict(task, sha, "READY" | "NOT_READY", findings)`, for the head
sha you reviewed. A verdict for an older sha is not binding.
