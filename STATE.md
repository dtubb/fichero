# STATE.md — Fichero

## 2026-06-05 — Session paused for sleep

**Branch:** `0.0.2` at `fa20d2b5` (`fix(workflows): remove dead citation dependency from Catalogue (#1665)`).

**Current focus:** Marshall IIIF/W3C import and staged workflow reliability. Do not break the mostly working `Catalogue` workflow; add staged workflows/chains beside it, then connect them.

**What is known:**
- SMB copy is still running: `copy_all_smb.sh` plus `rsync` for the 1928 enhanced documents. `_stage` is about 11G.
- Best user-test library so far: `/Users/danieltubb/code/marshall_diaries/Marshall10Entities-064359.fichero`.
- 5-page and 10-page Marshall imports verify with thumbnails/display 200, transcript artifacts, imported W3C entities, page entities, KG claims, and folder catalogue artifacts.
- 20-page import verifies imported artifacts/entities/images, but workflow claim/folder outputs did not complete visibly; this is tracked on #1665/#1673.

**Open issue cluster:**
- #1669 staged Catalogue split.
- #1673 long-stage page progress/checkpoint visibility.
- #1674 imported vs extracted entity provenance layers.
- #1675 reversible merge/split audit trail.
- #1676 post-entity SVO/KVO stage.
- #1677 SwiftUI review UI for staged layers.
- #1678 ontological KG layer.

**Next session — start here:**
- Check `pgrep -fl 'copy_all_smb|rsync'` and `du -sh ~/code/marshall_diaries/_stage`; keep the copy alive.
- Continue adding additive staged workflow presets/chain scaffolding in `fichero-engine/src/fichero/resources/default_workflows/` and chain APIs without modifying `catalogue.json`.
- Inspect `fichero-engine/src/fichero/workflows/chaining.py` and `fichero-engine/src/fichero/api/routes/chains.py` before editing chain behavior.
- Add focused tests around default workflow seeding/chain presets, then commit only the scoped diff.
- Resume scale testing at 20 pages after workflow progress/checkpoint fixes; do not move to full corpus until 20 is green.
