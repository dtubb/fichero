"""Unit tests for remote HPC batch helper primitives (#657)."""

from pathlib import Path

from fichero_server.workflows.remote_jobs import (
    SlurmJobConfig,
    build_bundle_manifest,
    build_slurm_script,
    parse_squeue_output,
    write_manifest,
)


def test_build_bundle_manifest_normalizes_paths():
    manifest = build_bundle_manifest(
        workflow_id="wf-1",
        workflow_name="Transcribe Batch",
        input_files=["./a.pdf", "/tmp/b.pdf"],
        library_path="./library.fichero",
        run_id="run-123",
        metadata={"source": "batch"},
    )
    assert manifest.workflow_id == "wf-1"
    assert manifest.input_files[0].endswith("a.pdf")
    assert manifest.library_path.endswith("library.fichero")
    assert manifest.metadata["source"] == "batch"


def test_write_manifest_persists_json(tmp_path: Path):
    manifest = build_bundle_manifest(
        workflow_id="wf-1",
        workflow_name="Workflow",
        input_files=["/tmp/a.pdf"],
        library_path="/tmp/lib.fichero",
        run_id="run-1",
    )
    out = write_manifest(manifest, tmp_path / "bundle" / "manifest.json")
    text = out.read_text(encoding="utf-8")
    assert '"workflow_id": "wf-1"' in text
    assert out.exists()


def test_build_slurm_script_with_gpu_and_extra_lines():
    script = build_slurm_script(
        config=SlurmJobConfig(
            job_name="fichero-ocr",
            partition="gpu",
            time_limit="04:00:00",
            cpus_per_task=8,
            mem_gb=32,
            gpus=1,
            extra_sbatch_lines=["#SBATCH --account=acenet-team"],
        ),
        remote_workdir="/scratch/user/fichero/run-1",
        runner_command=["python", "runner.py", "--manifest", "manifest.json"],
    )
    assert "#SBATCH --job-name=fichero-ocr" in script
    assert "#SBATCH --partition=gpu" in script
    assert "#SBATCH --gres=gpu:1" in script
    assert "#SBATCH --account=acenet-team" in script
    assert "python runner.py --manifest manifest.json" in script


def test_parse_squeue_output():
    parsed = parse_squeue_output(
        "12345|RUNNING\n67890|PENDING\ninvalid-line\n\n"
    )
    assert parsed == {"12345": "RUNNING", "67890": "PENDING"}
