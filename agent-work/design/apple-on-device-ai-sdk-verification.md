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

## MLX in the Foundation Models API — partly real, and not for macOS 26

Claim under test (WWDC26 session 232, "Run local agentic AI on the Mac using
MLX"): mlx-community models drop into the Foundation Models API. Verified
against the same swiftinterface, plus the SDK's framework list.

**There is no MLX in the SDK.** 331 frameworks under
`MacOSX.sdk/System/Library/Frameworks`, none of them MLX; no private MLX
framework either. Nothing in FoundationModels loads weights: no
safetensors/GGUF path, no Hugging Face hub type, no "custom model" loader.
`SystemLanguageModel.Adapter` is the LoRA-adapter mechanism (Background
Assets `AssetPack`, `compatibleAdapterIdentifiers`) — a fine-tune ON the
system model, not arbitrary community weights.

**What is actually there is an extensibility seam**, and it is the real story:

```swift
public protocol LanguageModel: Sendable {            // macOS 27.0
  associatedtype Executor: LanguageModelExecutor where Self == Self.Executor.Model
  var capabilities: LanguageModelCapabilities { get }
  var executorConfiguration: Self.Executor.Configuration { get }
}
public protocol LanguageModelExecutor: Sendable {    // macOS 27.0
  func respond(to: LanguageModelExecutorGenerationRequest,
               model: Self.Model,
               streamingInto: LanguageModelExecutorGenerationChannel) async throws
}
```

`LanguageModelSession` has `init(model: some LanguageModel, …)`, so a model
backed by mlx-swift genuinely CAN become a Foundation Models session with the
same `Transcript` / tool / streaming shape. That is the unlock: **bring your
own executor**, not Apple shipping MLX.

Three things that do NOT come for free — the part a blog post drops:

1. **`@available(macOS 27.0)` on both protocols.** Our
   `MACOSX_DEPLOYMENT_TARGET` is `26.0`. Same gate as Private Cloud Compute.
   (`LanguageModelSession` itself is macOS 26, so today's fm-bridge is
   unaffected; only the extensibility is future-OS.)
2. **Guided generation is handed to you, not done for you.** The executor
   receives `schema: GenerationSchema?` and `enabledToolDefinitions` in its
   request and must HONOUR them. Constrained decoding and tool-calling are the
   executor's job. mlx can do it (logit processors / grammars), but it is work
   — it is not the decoder-level guarantee we get from
   `SystemLanguageModel`, which is the entire reason we route structured
   extraction to Apple today.
3. **Capabilities are self-declared.** `LanguageModelCapabilities` (`.vision`,
   `.guidedGeneration`, `.reasoning`, `.toolCalling`) is a statement the model
   makes about itself, enforced by nobody — the same shape as the
   `apple-intelligence` row that claimed vision it did not have.

**Recommendation: do not converge the MLX path onto this.** mlx-swift is a
separate SPM package and our MLX serving is Python (`mlx_vlm`, the managed
server). Writing a `LanguageModelExecutor` would mean re-implementing MLX
serving in Swift — a SECOND serving surface, not a smaller one — for an API
we cannot call on our deployment target. Revisit if the target ever moves to
macOS 27, and coordinate with lane-mlx-catalog then; nothing about it changes
what the Apple provider rows do today.
