# Worker Queue — 0.0.2 backend autonomous loop
# Generated: 2026-05-17

- issue: 834
  status: done
  title: "Apple Vision OCR returns empty silently on hard pages — log + retry-with-fast-level"
  files: [fichero-engine/src/fichero/ocr/, fichero-engine/src/fichero/transcribe/]
  approach: "On empty Vision result, log warning + retry at .fast recognition level; surface error if still empty after retry."
  est_tokens: 18000
  blocked_reason: null
  commit: e89d8725
  completed_at: 2026-05-17T14:18:00Z

- issue: 1085
  status: pending
  title: "Maps importer: pair sidecar .iffy.json files with their image/PDF on ingest"
  files: [fichero-engine/src/fichero/ingest/]
  approach: "During ingest, detect sibling <name>.iffy.json and persist its contents as metadata on the Document; no schema migration needed."
  est_tokens: 20000
  blocked_reason: null
  commit: null
  completed_at: null

- issue: 840
  status: pending
  title: "Save per-chunk catalogue summaries as catalogue.chunk.N artifacts (transparency)"
  files: [fichero-engine/src/fichero/workflows/nodes/catalogue.py, fichero-engine/src/fichero/models/artifact.py]
  approach: "Emit one Artifact per chunk with type catalogue.chunk.N before final catalogue artifact; keep final artifact unchanged."
  est_tokens: 25000
  blocked_reason: null
  commit: null
  completed_at: null
