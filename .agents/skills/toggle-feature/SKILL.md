---
description: Enable or disable a feature flag for dev or release builds.
name: toggle-feature
---

# Toggle Feature

Enable or disable a feature flag. This skill will be fully defined after the feature flag system is designed (Pass 5 of the ralph loop). For now, this is a placeholder that documents the intended interface.

## Inputs

- `feature`: Feature name (must match a row in the feature matrix)
- `state`: "on", "off", or "dev-only"
- `side`: "frontend", "backend", or "both"

## Steps (to be defined after feature flag design)

1. Locate the flag definition (Swift side and/or Python side)
2. Update the flag to the requested state
3. Verify the change compiles / passes basic checks
4. Report the change

## Notes

This skill is intentionally incomplete. It will be filled in during the feature-flag-design pass of the ralph loop once we know whether flags are compile-time, runtime, environment-based, or config-file-based.
