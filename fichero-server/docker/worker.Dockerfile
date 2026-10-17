# Fichero's slim worker image: what a cluster pulls ONCE into /project (`apptainer pull`) and runs a read shard in
# (`compute.hpc.slim-worker-image`). amd64, no MLX, no engine: just the runner's own dependencies, installed from
# the PEP 723 header of runner.py so this image and a Hugging Face Job can never disagree about them.
# The runner itself ships with each read package (_fichero/runner.py); it is copied here only for its header.
#
# Build (context = the fichero-server dir):
#   docker build --platform linux/amd64 -f docker/worker.Dockerfile -t fichero-worker:dev .
# On a cluster (as the person, no root):
#   apptainer pull fichero-worker.sif docker://ghcr.io/<owner>/fichero-worker:<tag>
FROM python:3.12-slim

# libgl/glib: pillow + kraken pull these at runtime on slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY src/fichero_server/remote_read/runner.py /tmp/runner.py
RUN uv pip install --system -r /tmp/runner.py && rm /tmp/runner.py

# Apptainer runs this as the calling user; an ordinary user here keeps the image honest about it.
RUN useradd --create-home --uid 10001 fichero
USER fichero
WORKDIR /package
