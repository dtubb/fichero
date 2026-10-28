"""The release smoke stops only the dev engine on the app's container socket, not other lanes' engines (#6244)."""

import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "smoke-release-embedded-backend.sh"
SOCK_UNDER_HOME = "Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock"


def _pattern(home: Path) -> str:
    line = next(ln for ln in SCRIPT.read_text().splitlines() if ln.startswith("DEV_ENGINE_PATTERN="))
    # Expand it the way bash would.
    out = subprocess.run(
        ["bash", "-c", f'{line}; printf %s "$DEV_ENGINE_PATTERN"'],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def test_the_pattern_matches_the_container_engine_only(tmp_path):
    pattern = _pattern(tmp_path)
    uv = "python -m uvicorn fichero_server.api.uds_transport:app --uds"
    assert re.search(pattern, f"{uv} {tmp_path}/{SOCK_UNDER_HOME} --ws websockets-sansio")
    assert not re.search(pattern, f"{uv} /tmp/lane-a/fichero.sock --ws websockets-sansio")


def test_every_pgrep_of_a_dev_engine_uses_the_pattern():
    text = SCRIPT.read_text()
    assert "uds_transport:app --uds'" not in text
    assert text.count('"$DEV_ENGINE_PATTERN"') >= 3
