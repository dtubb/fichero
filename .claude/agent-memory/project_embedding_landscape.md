---
name: embedding-landscape-feasibility
description: Research findings on 3D embedding landscape (t-SNE/UMAP flythrough) for the archive, mapped onto Fichero's existing SpatialScene3D + LanceDB stack
metadata:
  type: project
---

Daniel asked (2026-06-15) whether Fichero could do a Google t-SNE Map-style 3D landscape flythrough of the archive.

**Finding:** The building blocks already exist. LanceDB stores embeddings (multilingual-e5-large, 1024-dim). SpatialScene3D (RealityKit) already renders nodes at backend-provided (x,y,z) coordinates with orbit camera, tap-to-select, and a 250-node cap. MindPalaceNode carries positionX/Y/Z. The missing piece is a backend `/api/spatial/projection` endpoint that reads all embedding vectors from LanceDB, runs UMAP/t-SNE to produce 2D or 3D coordinates, and returns them as node positions.

**Why:** Daniel wants a Tinderbox-for-archives "fly through your archive" discovery mode where similar documents cluster.

**How to apply:** Recommend umap-learn with `.transform()` for incremental adds; backend endpoint returns coordinate JSON; SpatialScene3D consumes it without changes to the renderer; 2D first (SpatialView 2D canvas), then promote to 3D. See [[mind-palace-milestone-mostly-done-fold-gated]] for spatial milestone context.
