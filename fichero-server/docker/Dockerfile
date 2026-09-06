# Fichero engine — host-agnostic OCI image (graph-remote / demo runner).
#
# Runs the WHOLE engine (FastAPI + DuckDB + workflow orchestrator) over a
# .fichero library bind-mounted into the container — the graph-remote topology
# of agent-work/design/hpc-remote-library-sync.md §4: data + compute co-located,
# not one image at a time.
#
# Deliberately host-agnostic: a plain `docker run` + one inbound port (8765), so
# the same image runs on a rented GPU (RunPod / Lambda / HF Docker Space) or, as
# a .sif via `apptainer build fichero-engine.sif docker-daemon://fichero-engine:latest`,
# on a raw-Slurm cluster (ACENET). No host is hard-coded.
#
# MLX is Apple-only and is NOT in the base [project].dependencies, so this Linux
# image builds clean; the local-model tier here is CUDA vLLM / CPU OCR (design §4.3).
#
# Build (context = the fichero-server dir):
#   docker build -f docker/Dockerfile -t fichero-engine:dev .
# Run (mount a library, expose the one port):
#   docker run --rm -p 8765:8765 \
#     -e FICHERO_BIND_HOST=0.0.0.0 \
#     -e FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK \
#     -e FICHERO_LIBRARY_ALLOWED_ROOTS=/data \
#     -v /path/to/Lib.fichero:/data/Lib.fichero \
#     fichero-engine:dev
#
# The 0.0.0.0 bind is deliberate and safe HERE: the container boundary is the
# perimeter, and the demo fronts the port with a tunnel/TLS. The engine's
# fail-closed default (127.0.0.1) is unchanged — this image opts in explicitly,
# exactly as bind_host.py requires.

FROM python:3.12-slim AS base

# libgl/glib: pillow + pypdfium2 rendering pull these at runtime on slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first (cached across source-only edits): copy just the metadata,
# then the source. pyproject's [project].dependencies is the single source of
# truth (kept in sync with the briefcase requires per the pyproject comment).
COPY pyproject.toml README* ./
COPY src ./src
RUN pip install .

# Non-root: the engine needs no privilege, and academic/rented hosts prefer it.
RUN useradd --create-home --uid 10001 fichero \
    && mkdir -p /data && chown -R fichero:fichero /data
USER fichero

# One inbound port — the engine's product port (bind_host.py / __main__.py).
EXPOSE 8765

# Library lives on a mounted volume; allow it as a library root.
ENV FICHERO_LIBRARY_ALLOWED_ROOTS=/data \
    FICHERO_BIND_HOST=0.0.0.0 \
    FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK

# The engine is its own entrypoint (python -m fichero_server → uvicorn on 8765).
CMD ["python", "-m", "fichero_server"]
