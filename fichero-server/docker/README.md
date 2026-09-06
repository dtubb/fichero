# Fichero engine container (graph-remote / demo)

Host-agnostic OCI image that runs the **whole** Fichero engine over a
`.fichero` library bind-mounted into the container — the **graph-remote**
topology of `agent-work/design/hpc-remote-library-sync.md` §4 (data + compute
co-located). Contrast with **model-remote** (`workflows/remote_jobs.py`), which
keeps the library on the Mac and ships one image at a time to Slurm.

## Build

Context is the `fichero-server/` directory:

```sh
cd fichero-server
docker build -f docker/Dockerfile -t fichero-engine:dev .
```

## Run (over a staged library)

```sh
docker run --rm -p 8765:8765 \
  -e FICHERO_LIBRARY_ALLOWED_ROOTS=/data \
  -v /path/to/MyLibrary.fichero:/data/MyLibrary.fichero \
  fichero-engine:dev
```

The engine listens on `:8765` inside the container. The `0.0.0.0` bind + the
non-loopback ack are baked into the image (see the Dockerfile header): the
container boundary is the perimeter, and the demo fronts the port with a
tunnel/TLS. The engine's fail-closed default (`127.0.0.1`) is unchanged — the
image opts in explicitly, exactly as `security/bind_host.py` requires.

## Where it runs

- **Rented GPU** (RunPod / Lambda / HF Docker Space): plain `docker run` + one
  inbound port. This is the credential-free 2-day demo host (design §4.5) — the
  choice of provider is Daniel's (D4); the image hard-codes none of them.
- **Raw-Slurm cluster** (ACENET, no Docker/root): convert once to Apptainer —
  `apptainer build fichero-engine.sif docker-daemon://fichero-engine:dev` — and
  `sbatch` the `.sif` with the staged package bind-mounted. Same image, cluster-legal wrapper.

## Notes

- **MLX is Apple-only** and is *not* in `[project].dependencies`, so this Linux
  image builds clean. The local-model tier here is CUDA vLLM / CPU OCR (design §4.3);
  hosted-API providers stay engine-side.
- The image installs from `pyproject.toml`'s `[project].dependencies`, the single
  source of truth kept in sync with the briefcase `requires`.
- Next slice (gated — check in before it touches the live transport): the
  pull-only sync routes + `fichero library clone` CLI, so a Mac clones/opens a
  container-hosted library live over the existing transport.
