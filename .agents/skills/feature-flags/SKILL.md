---
description: Design and implement a feature flag system for this project. Reads the tech stack from AGENTS.md and proposes an appropriate approach. Works for Swift, Python, or mixed projects.
name: feature-flags
---

# /feature-flags

Design a feature flag system that lets you toggle features on/off for dev vs release builds. Reads the tech stack from `AGENTS.md` — adapts to Swift, Python, or any combination.

## Step 1 — Read the stack

From `AGENTS.md`:
- What language(s)? (Swift, Python, JS, etc.)
- What's the build system? (Xcode, pip, npm, etc.)
- Is there a dev vs release distinction already? (debug builds, env vars, config files)
- What features exist? (from architecture section)

## Step 2 — Propose an approach

Based on the stack, propose one of these patterns:

**Swift / Xcode:**
```swift
// FeatureFlags.swift — single source of truth
enum FeatureFlag: String, CaseIterable {
    case myFeature = "my_feature"
    case anotherFeature = "another_feature"
}

struct FeatureFlags {
    static func isEnabled(_ flag: FeatureFlag) -> Bool {
        #if DEBUG
        return debugFlags[flag] ?? false
        #else
        return releaseFlags[flag] ?? false
        #endif
    }
    private static let debugFlags: [FeatureFlag: Bool] = [
        .myFeature: true,
    ]
    private static let releaseFlags: [FeatureFlag: Bool] = [
        .myFeature: false,
    ]
}
```

**Python:**
```python
# feature_flags.py — single source of truth
import os

class FeatureFlags:
    _flags = {
        "my_feature": os.getenv("FEATURE_MY_FEATURE", "false").lower() == "true",
    }

    @classmethod
    def is_enabled(cls, flag: str) -> bool:
        return cls._flags.get(flag, False)
```

**Mixed (Swift frontend + Python backend):**
- Backend owns flag state (single source of truth)
- Frontend reads flags from an API endpoint at startup
- Both use the same flag names

Present the proposed approach to Daniel for approval before implementing.

## Step 3 — Inventory features to flag

From the feature audit (run `/feature-audit` first if not done), identify:
- Features that are built but not ready for release → flag as OFF in release
- Features under active development → flag as OFF in release, ON in dev
- Experimental features → flag as OFF everywhere until approved

## Step 4 — Implement (after approval)

1. Create the flag file(s) in the right location per `AGENTS.md`
2. Add all identified features to the flag inventory
3. Wrap the relevant code paths with flag checks
4. Add a test that verifies flags default correctly per environment

## Step 5 — Document

Add to `AGENTS.md` under Architecture:
```
## Feature Flags
Flags live in [file]. Add new flags there. Dev: [how to enable]. Release: [how to verify].
```

Update `MEMORY.md` with the flag system location and pattern.

## Step 6 — Report

List all flags created, their default states (dev / release), and which code paths they guard.
