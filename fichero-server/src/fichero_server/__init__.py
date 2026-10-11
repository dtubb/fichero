"""
Fichero - Document Processing and Transcription

The GUI is now a separate Swift app.
Use `fichero serve` to start the API server.
"""

__version__ = "0.1.0-dev"

# Every Hugging Face cache points into Fichero's model store before any library that reads them is imported
# (`runtime.models-in-the-store`): this package is the first module uvicorn and the embedded engine both import.
from fichero_server.db.paths import pin_hf_caches as _pin_hf_caches  # noqa: E402

_pin_hf_caches()

__all__ = ["__version__"]
