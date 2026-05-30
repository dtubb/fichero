# Milestone Audit — "Website" — 2026-05-30

**Scope reminder:** "Website" = tubb.ca/fichero public site, release notes, download page, dev blog, end-user docs published as static site. Distinct from "Documentation" (user-manual content), "Exporter" (app feature), "Developer Experience" (contributor tooling).

**Milestone #66 state:** open · 3 open issues · 0 closed issues

---

## Summary counts

| Action | Count |
|---|---|
| Keep (no change) | 0 |
| Close as duplicate | 1 |
| Label edits | 3 |
| Reopen / re-milestone | 0 |

---

## CLOSE AS DUPLICATE

```bash
# #661 is superseded by #662
# Both cover: download page at tubb.ca/fichero, download link, appcast.xml, system requirements
# #662 adds release notes + "for 0.0.2" specificity, making it the canonical version
gh issue close 661 \
  --repo dtubb/fichero \
  --reason "not planned" \
  --comment "Superseded by #662, which captures the same scope (download page, appcast.xml, system requirements) and additionally specifies 0.0.2 release notes and a feature overview. Closing as duplicate."
```

---

## LABEL EDITS

All three issues carry `client:swiftui`, which is wrong — these are tubb.ca website tasks, not Mac app tasks. `client:swiftui` means "Mac SwiftUI app surface"; none of these issues touch the Swift app.

None of the three issues have a `priority:*` or `tier:*` label.

**Canonical additions needed on all three:**
- Remove: `client:swiftui`
- Add: `priority:P2` (non-blocking, no user-visible app regression; website polish)
- Add: `tier:medium` (standard writing/templating work, no architectural decisions)

**Issue #665** — "Write dev blog post: building Fichero — 3 years of 100% AI-assisted coding"

```bash
gh issue edit 665 \
  --repo dtubb/fichero \
  --remove-label "client:swiftui" \
  --add-label "priority:P2,tier:medium"
# Rationale: blog post is pure site content; no SwiftUI surface; P2 (nice-to-have, not blocking any release); tier:medium (drafting + editing)
```

**Issue #662** — "Update tubb.ca/fichero with release notes, download link, and feature overview for 0.0.2"

```bash
gh issue edit 662 \
  --repo dtubb/fichero \
  --remove-label "client:swiftui" \
  --add-label "priority:P1,tier:medium"
# Rationale: download page + appcast.xml are release-blocking for real-user distribution; escalate to P1 vs blog post; tier:medium
```

**Issue #661** — "Add Fichero download page to tubb.ca" (will be closed above, but label-fix it first so history is clean)

```bash
gh issue edit 661 \
  --repo dtubb/fichero \
  --remove-label "client:swiftui" \
  --add-label "priority:P2,tier:medium"
# Rationale: correct label drift before closing; P2 because #662 supersedes with more detail
```

---

## KEEP (no changes beyond above)

| # | Title | Decision |
|---|---|---|
| #665 | Write dev blog post | Keep open, label fix applied above |
| #662 | Update tubb.ca with release notes / download / 0.0.2 | Keep open, label fix + P1 applied above |

---

## TRICKY CASES

### #661 vs #662 overlap
#661 ("Add Fichero download page") and #662 ("Update tubb.ca/fichero with release notes, download link, and feature overview for 0.0.2") share acceptance criteria nearly verbatim (download link → fichero-releases release asset, appcast.xml at tubb.ca/fichero/appcast.xml, macOS 15+ Apple Silicon requirement). #662 is strictly a superset: it adds the "0.0.2" version peg and release notes. Closing #661 as not-planned is the correct call; no work is lost.

### No `documentation` label on #665
The blog post issue (#665) could take the `documentation` label, but the canonical list has `documentation` as a standalone label without a `type:` prefix, and #665 already has `type:task`. Adding `documentation` would be consistent (it IS documentation content) but is optional; left out of the proposal to keep the change minimal. Manager may add if desired.

### Missing `client:html`?
The `client:html` label is defined as "Exporter static-HTML + document_view.html" — that is the *app Exporter feature*, not the tubb.ca website. None of these issues should carry `client:html`. The website surface has no dedicated `client:` label in the canonical 23; omitting it is correct.

### Milestone description accuracy
The milestone description says "end-user documentation site (the docs/user-guide/ Markdown gets published here)." The "Documentation" milestone (#67, currently empty) is described separately. This creates potential future confusion about where issues for user-guide publishing live. Not an issue-level action, but worth a note to Daniel: decide whether "republish user-guide as static site" tasks live in "Website" or "Documentation."
