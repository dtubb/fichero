import pytest

GB = 1024**3


@pytest.fixture
def plenty_of_memory(monkeypatch):
    """A Mac with 64 GB, whatever this one has: a test that starts a default model must not depend on
    the RAM of the machine running it (an 8 GB Air refused Qwen3-VL 8B, #5528)."""
    from fichero_server.llm import kraken_runtime, local_inference

    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", lambda: 64 * GB)
    monkeypatch.setattr(local_inference, "_sysctl_memory_bytes", lambda: 64 * GB)
    local_inference.get_local_inference_capabilities.cache_clear()
    yield
    monkeypatch.undo()  # the cache is cleared after the test's own patches of it are gone too
    local_inference.get_local_inference_capabilities.cache_clear()
