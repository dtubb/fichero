# The GPU worker: the slim worker image plus vLLM (which brings CUDA PyTorch), for the offline-batch vision reader
# (`compute.hpc.vllm-offline-reader`, `compute.image.full-and-worker`). No MLX. amd64 only.
# Build the slim image first, then:
#   docker build --platform linux/amd64 -f docker/worker-gpu.Dockerfile --build-arg BASE=fichero-worker:dev -t fichero-worker-gpu:dev .
ARG BASE=ghcr.io/dtubb/fichero-worker:latest
FROM ${BASE}
USER root
# Pinned: bump on purpose.
RUN uv pip install --system vllm==0.31.0
USER fichero
