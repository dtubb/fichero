"""Coverage for kreuzberg cache environment routing."""

import os
import subprocess
import sys


def test_explicit_kreuzberg_cache_dir_is_preserved():
    env = os.environ.copy()
    env["KREUZBERG_CACHE_DIR"] = "/tmp/fichero-test-kreuzberg"
    result = subprocess.run(
        [sys.executable, "-c", "import os; import fichero_server.loaders.kreuzberg_cache; print(os.environ['KREUZBERG_CACHE_DIR'])"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "/tmp/fichero-test-kreuzberg"
