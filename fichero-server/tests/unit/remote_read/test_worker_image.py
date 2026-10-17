"""The slim worker image (`compute.hpc.slim-worker-image`): what the cluster pulls once with `apptainer pull`."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOCKERFILE = ROOT / "fichero-server" / "docker" / "worker.Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "worker-image.yml"


def test_the_worker_image_installs_the_runners_own_dependencies_and_runs_as_nobody_special():
    """WHY: one dependency list (the runner's PEP 723 header, so the image and a Hugging Face Job cannot drift);
    no MLX, no engine; an ordinary user, because Apptainer runs as the person."""
    text = DOCKERFILE.read_text()
    assert "runner.py" in text and re.search(r"uv pip install .*-r .*runner\.py", text)
    assert not re.search(r"pip install [^-\n]*\b(kraken|pillow|torch|mlx)", text), "name no package of its own"
    assert "mlx" not in text.lower().replace("no mlx", "")
    assert re.search(r"^USER \S+", text, re.M) and "USER root" not in text


def test_ci_builds_amd64_checks_the_imports_and_publishes_for_apptainer_pull():
    text = WORKFLOW.read_text()
    assert "linux/amd64" in text and "worker.Dockerfile" in text
    assert "import kraken" in text, "the import check"
    assert "ghcr.io" in text and "push:" in text
