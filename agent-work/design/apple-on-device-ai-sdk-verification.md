# Apple on-device AI: what the SDK actually offers (2026-09-04)

Verification for items 2–4 of `agent-work/specs/apple-on-device-ai-program.md`,
read from the **installed SDK's swiftinterface**, not from docs or memory:

```
/Applications/Xcode-beta.app/…/MacOSX.sdk/System/Library/Frameworks/
  FoundationModels.framework/Modules/FoundationModels.swiftmodule/
    arm64e-apple-macos.swiftinterface
  Translation.framework/…/arm64e-apple-macos.swiftinterface
```

No build was run. Every claim below is a line in one of those files.

## 2. Guided generation — ALREADY BUILT, do not build it again

`fichero-server/bin/fm-bridge/FmBridge.swift` (481 lines) already maps a
Pydantic schema onto `FoundationModels.DynamicGenerationSchema` and
`llm/__init__.py:chat_structured` routes `provider="apple"` to it. The decoder
is constrained at the token level, which is the whole point: malformed
structure cannot be emitted. The error taxonomy (guardrail violation, context
window exceeded, rate limited, assets unavailable) is already mapped too.

What was actually missing was an honest **description** of the row, not a
bridge: `apple-intelligence` was served to the +Add Model browser with
`supports_vision=True` while its canonical capabilities are `["text"]`.
Foundation Models take no image input — fm-bridge opens a
`SystemLanguageModel` session and there is no image path in it. Fixed, with a
test that holds the two sources against each other (`f8e7635`).

**Remaining work is the CONSUMERS**, not the plumbing: subject-naming for
spaCy candidate triples and date/place normalization, whose schemas need
agreeing with lane-svo-quality.

## 3. Private Cloud Compute — real, but macOS 27

`PrivateCloudComputeLanguageModel` exists, with `availability`
(`.deviceNotEligible` / `.systemNotReady`), `contextSize`, `supportedLanguages`,
`supportsLocale(_:)`, and a typed error set. It conforms to `LanguageModel`,
and `LanguageModelSession` has a generic `init(model: some LanguageModel, …)`
— so fm-bridge can host it without a second bridge.

Two facts that change the plan:

- **`@available(iOS 27.0, macOS 27.0, …)`.** The app's
  `MACOSX_DEPLOYMENT_TARGET` is `26.0`. This is a FUTURE-OS API for us: it
  needs an `if #available(macOS 27, *)` gate and an honest "not available on
  this system" state on 26, not a plain second model row.
- **It has a QUOTA**: `quotaUsage`, `.quotaLimitReached`, and a
  `limitIncreaseSuggestion`. "No API cost" is true; "unlimited" is not. A
  quota refusal must surface as a typed error — never a silent fall-through
  to a paid cloud, which is the one thing the prefer-raise rule forbids.

**Needs a ruling before any code**: is a macOS-27-only tier in scope for a
product that targets macOS 26?

## 4. Translation — usable headless, which was the open question

The worry was that `TranslationSession` is a SwiftUI-attached object
(`.translationTask`), which would put it in the app process rather than in a
bridge the engine can call. It is not:

- `convenience init(installedSource:target:)` — a session with no view.
- `translate(_ string:)` and `translate(batch:)` — free functions on it.
- `LanguageAvailability.status(from:to:)` — decides installed vs not.

So Translation fits the fm-bridge pattern exactly: a second subcommand, same
subprocess seam, same JSON protocol. Core API is macOS 26.0 (`Strategy`
/`.highFidelity` and `AttributedString` requests are 26.4 — optional extras we
can gate or skip).

One constraint to design around: **downloading a language pair needs the UI**
(`canRequestDownloads`). The engine must refuse with a reason naming the pair
and let the app request the download; it must never appear to translate while
a model is missing.

## What is blocked on a machine slot

- The 3-page spot-check (Translation vs the LLM translate step) — real pages,
  both paths, side-by-side table. Model-invoking; needs a slot.
- Compiling any new fm-bridge subcommand (`swiftc`, seconds, but a build).
