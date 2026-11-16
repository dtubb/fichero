"""By hand, not a test or a guard: the CLAHE enhance against the legacy tool's own output on the owner's typed pages
(`image.enhance.contrast-clahe`, #6190). The pages are archive material and are never committed.

    FICHERO_IMAGE_PREP_SAMPLES=<folder> PYTHONPATH=fichero-server/src python -m fichero_server.media.image_prep_samples

The folder holds, for each page, `<name>.before.<ext>` (the legacy crop) and `<name>.reference.<ext>` (the legacy enhanced file), and
optionally `<name>.profile` containing `handwritten` or `typescript` (default handwritten). Exit 0 when every page's mean absolute
difference per channel is under 3/255; exit 1 otherwise; exit 2 when the variable is unset or the folder has no pair.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

THRESHOLD = 3.0


def pairs(root: Path) -> list[tuple[str, Path, Path, str]]:
    out = []
    for before in sorted(root.glob("*.before.*")):
        name = before.name.split(".before.")[0]
        reference = next(iter(sorted(root.glob(f"{name}.reference.*"))), None)
        if reference is not None:
            profile_file = root / f"{name}.profile"
            out.append((name, before, reference, profile_file.read_text().strip() if profile_file.is_file() else "handwritten"))
    return out


def main() -> int:
    folder = os.environ.get("FICHERO_IMAGE_PREP_SAMPLES")
    found = pairs(Path(folder)) if folder and Path(folder).is_dir() else []
    if not found:
        print("FICHERO_IMAGE_PREP_SAMPLES is unset or holds no <name>.before.* / <name>.reference.* pairs")
        return 2
    import numpy as np
    from PIL import Image

    from fichero_server.media.image_ops import apply_operation

    worst = 0
    for name, before, reference, profile in found:
        with Image.open(before) as opened:
            page = opened.convert("RGB")
        out = apply_operation(page, {"op": "enhance", "params": {"method": "clahe", "profile": profile}})
        with Image.open(reference) as opened:
            want = opened.convert("RGB").resize(out.size)
        diff = float(np.abs(np.asarray(out, "float32") - np.asarray(want, "float32")).mean())
        print(f"{name} ({profile}): mean difference {diff:.2f}/255, limit {THRESHOLD}: {'ok' if diff < THRESHOLD else 'TOO FAR'}")
        worst = max(worst, 0 if diff < THRESHOLD else 1)
    return worst


if __name__ == "__main__":
    sys.exit(main())
