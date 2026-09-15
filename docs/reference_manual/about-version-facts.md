(AI generated. Not reviewed.)

# About & Version Facts

Reference for the facts shown in the About window and how they are derived. Design intent:
`docs/contributor_manual/specs/ui/about.md`. Implementation: `docs/contributor_manual/ui-about.md`.

## Fields

| Field | Source | Format |
|---|---|---|
| App name | constant | `Fichero` |
| App version + build | `CFBundleShortVersionString` + `CFBundleVersion` | `Version <short> (<build>)`; each missing/blank part renders as `—` |
| Server / engine version | `AppState.backendVersion` (health cache) | `Server <date>`; PEP 440 re-padded to the display date form; **row omitted when unknown** |
| Icon | running app icon (`NSApp.applicationIconImage` on macOS; highest-res `CFBundleIconFiles` on iOS) | 96×96, decorative |
| Copyright | bundle `NSHumanReadableCopyright`, else fallback | fallback: `© 2025–2026 Daniel Tubb · AGPL-3.0` |
| License | `AboutLinks.license` | `https://github.com/dtubb/fichero/blob/main/LICENSE` (AGPL-3.0) |
| Repository | `AboutLinks.repository` | `https://github.com/dtubb/fichero` |

## Version formats

- **App (display) version** — the calendar date form with zero-padded month/day, e.g. `2026.09.15`.
- **Engine (PEP 440) version** — the engine reports the no-leading-zero form, e.g. `2026.9.15`,
  with an optional beta suffix `bN`. About re-pads it for display so the same release is never
  shown two different ways:
  - `2026.9.3` → `2026.09.03`
  - `2026.9.3b1` → `2026.09.03-beta`
  - `2026.9.3b2` → `2026.09.03-beta.2`
  - non-calendar strings (e.g. `1.2`, `dev`) pass through unchanged.

## Acknowledgements (open-source stack)

Grouped into three layers, in display order:

1. **App (Swift)** — SwiftUI & AppKit, Sparkle, PythonKit, Swift OpenAPI Generator, SwiftNIO,
   Swift Crypto & Certificates, Swift Collections/Algorithms/Numerics, Swift Argument Parser,
   AsyncHTTPClient, OpenAPIKit, Yams.
2. **Engine (Python)** — FastAPI, Starlette, Uvicorn, Pydantic, DuckDB, LanceDB, LangChain,
   LangGraph, Model Context Protocol (MCP), spaCy, Kreuzberg, PyMuPDF, pypdfium2, Pillow, OpenCV,
   fastembed, NumPy, httpx, Rich & Typer, Jinja2, rdflib, PyObjC.
3. **On-device AI** — MLX (mlx-lm, mlx-vlm, mlx-whisper), Kraken, Whisper.

Each entry carries a name, license, project URL, and a `versionKey` (its lowercased pip/SPM
distribution name — e.g. MCP → `mcp`, OpenCV → `opencv-python-headless`, MLX → `mlx-lm`). When the
engine's health report includes a dependency's version, the sheet shows `v<version> · <license>`;
otherwise it shows the license alone (never a stale pinned number). The list is curated but derived
from the real manifests (`Package.resolved`, `fichero-server/pyproject.toml`, the runtime
provisioner); refresh it against those when dependencies change.
