# 0.1.0 QA Sign-Off Checklist

Use this checklist for the 0.1.0 release gate. Attach failures to GitHub issues
with repro steps, expected behavior, actual behavior, logs/screenshots, and the
tested commit.

## Preconditions

- [ ] App version and build number match the release candidate.
- [ ] Fresh install launches without using a developer checkout.
- [ ] Existing library opens after upgrade.
- [ ] New empty library can be created.
- [ ] Backend health indicator reaches ready.

## Core Library

- [ ] Import a PDF, image, text file, and folder.
- [ ] Link mode preserves original file paths.
- [ ] Copy mode stores files inside the `.fichero` package.
- [ ] Sidebar selection, grid/list selection, and inspector selection stay in sync.
- [ ] Rename, move, duplicate, and delete show expected undoable behavior.

## Reading Surface

- [ ] PDF preview renders a multi-page PDF.
- [ ] Image preview renders without stretching or clipping controls.
- [ ] Text/content pane displays extracted text.
- [ ] Inspector tabs switch without blanking the selected document.
- [ ] Knowledge surface opens for a document with claims.

## Search And KG

- [ ] Text search returns expected imported documents.
- [ ] Saved search persists after relaunch.
- [ ] KG entity browser opens and can navigate to a source document.
- [ ] Related claims panel shows claims for the selected document.

## Workflows And Activity

- [ ] Catalogue workflow can be started on a small fixture library.
- [ ] Activity view shows the running workflow.
- [ ] Completed run shows status, log, and artifacts.
- [ ] Failed run surfaces a readable error.

## Release Outputs

- [ ] DMG is Developer ID signed, notarized, stapled, and opens on a clean Mac.
- [ ] Sparkle update feed points at the GitHub appcast and validates.
- [ ] TestFlight build uploads and installs for internal testing.
- [ ] Release notes mention known limitations and upgrade notes.

## Sign-Off

- [ ] No open P0/P1 bugs remain.
- [ ] Deferred issues are explicitly moved to later milestones.
- [ ] Daniel approved this release candidate.

Sign-off commit:

Sign-off date:

Tester:
