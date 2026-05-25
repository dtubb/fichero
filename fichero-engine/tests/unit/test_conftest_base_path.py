from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path


def _load_conftest_module():
    conftest_path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "fichero_engine_tests_conftest",
        conftest_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_test_base_path_is_per_process_and_unique() -> None:
    conftest = _load_conftest_module()
    path1 = conftest._make_test_base_path()
    path2 = conftest._make_test_base_path()

    try:
        assert path1 != path2
        assert str(os.getpid()) in path1.name
        assert str(os.getpid()) in path2.name
        assert path1.exists()
        assert path2.exists()
    finally:
        shutil.rmtree(path1, ignore_errors=True)
        shutil.rmtree(path2, ignore_errors=True)
