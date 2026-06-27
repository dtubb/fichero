---
description: Publish a Fichero release — create GitHub release, upload DMG, update appcast, deploy site to tubb.ca. Run only after Daniel has reviewed /fichero-release-prep output.
name: fichero-release
---

# /fichero-release

Publish the prepared release. Only run after `/fichero-release-prep` and Daniel's approval.

## Pre-check

Before doing anything, confirm:
1. `build/releases/Fichero.dmg` exists
2. `build/releases/release-manifest.txt` exists
3. Daniel has reviewed the DMG and release notes

If any of these are missing, tell Daniel to run `/fichero-release-prep` first.

## Steps

### 1. Commit release notes

```bash
git add site/docs/index.md
git commit -m "docs: update release notes for v[version]"
```

### 2. Create GitHub release and upload DMG

```bash
bash scripts/create-github-release.sh
```

This creates a GitHub release, uploads the DMG, and updates `appcast.xml`.

### 3. Commit and push appcast

```bash
git add fichero-swiftui/appcast.xml
git commit -m "chore: update appcast for v[version]"
git push
```

### 4. Deploy site to tubb.ca

```bash
bash scripts/deploy-site.sh
```

### 5. Sparkle signing reminder

Remind Daniel:
```
Sign the appcast entry with your Sparkle private key:
  sign_update build/releases/Fichero.dmg
Then replace SIGN_WITH_SPARKLE_PRIVATE_KEY in fichero-swiftui/appcast.xml
Commit and push the signed appcast.
```

### 6. Report

```
FICHERO RELEASE — v[version] — [date]

GitHub release: [URL]
DMG uploaded:   ✓
Appcast:        Updated (needs Sparkle signature)
Site deployed:  ✓

Remaining manual step: sign appcast with Sparkle private key
```
