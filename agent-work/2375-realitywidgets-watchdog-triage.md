# #2375 VisionOS RealityWidgets watchdog triage

Classification: likely simulator/runtime noise during visionOS launch, not a Fichero-owned RealityWidgets integration.

Evidence:
- No `WidgetKit` / widget extension target or `com.apple.RealityWidgets` reference exists in `fichero/fichero.xcodeproj/project.pbxproj`.
- The visionOS-specific app entry is `fichero/fichero/FicheroApp_iOS.swift`; it only contains guarded QR/capture fallbacks and no widget or RealityWidgets launch path.
- Remaining RealityKit usage in the repo is in optional `#if canImport(RealityKit)` spatial views, which does not imply a widget/RealityWidgets launch chain.

Recommended manager verification / workaround:
- Re-run the same visionOS simulator launch after clearing DerivedData or resetting the simulator runtime to confirm the watchdog is reproducible outside this worktree.
- Compare against a minimal blank visionOS app on the same simulator/runtime.
- If the crash persists with no Fichero process-side evidence, treat it as simulator/runtime launch noise rather than an app regression.

