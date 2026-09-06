"""Unit tests for the HPC/Slurm wiring helpers in remote_jobs.py.

Covers the first-slice additions from the Fichero ⇄ HPC live-connection plan:
cluster config validation, Slurm→RunStatus mapping, array-directive rendering
(incl. sparse resubmission lists), the run-spec builder, and the scriptable
DryRunSubmitter fake — all pure, no cluster required (plan §8).
"""

import pytest

from fichero_server.workflows.remote_jobs import (
    DryRunSubmitter,
    HpcClusterConfig,
    HpcConfigError,
    build_array_directive,
    build_bundle_manifest,
    build_remote_run_spec,
    build_sinfo_probe_command,
    build_ssh_command,
    is_terminal_slurm_state,
    map_slurm_state,
    normalize_slurm_state,
)
from fichero_server.workflows.run_status import RunStatus


def _cluster(**overrides) -> HpcClusterConfig:
    base = dict(
        cluster_id="c1",
        name="ACEnet",
        host_alias="acenet",
        username="researcher",
        remote_base_dir="/scratch/researcher",
        partition="gpu",
        account="def-lab",
    )
    base.update(overrides)
    return HpcClusterConfig(**base)


# ---------------------------------------------------------------------------
# HpcClusterConfig validation
# ---------------------------------------------------------------------------


class TestClusterConfig:
    def test_valid_config_passes(self):
        _cluster().validate()  # no raise

    @pytest.mark.parametrize(
        "field", ["name", "host_alias", "username", "remote_base_dir", "partition"]
    )
    def test_missing_required_field_raises(self, field):
        with pytest.raises(HpcConfigError) as exc:
            _cluster(**{field: "  "}).validate()
        assert field in str(exc.value)

    def test_relative_remote_base_dir_rejected(self):
        with pytest.raises(HpcConfigError):
            _cluster(remote_base_dir="scratch/me").validate()

    def test_bad_ssh_port_rejected(self):
        with pytest.raises(HpcConfigError):
            _cluster(ssh_port=99999).validate()

    def test_remote_workdir_is_run_scoped(self):
        wd = _cluster().remote_workdir("run-42")
        assert wd == "/scratch/researcher/fichero/runs/run-42"

    def test_round_trips_through_dict(self):
        cfg = _cluster()
        assert HpcClusterConfig.from_dict(cfg.to_public_dict()) == cfg

    def test_to_public_dict_has_no_secret_fields(self):
        # The whole point of §4: only config references, never key material.
        keys = set(_cluster().to_public_dict())
        assert not (keys & {"password", "api_key", "key", "secret", "token"})


# ---------------------------------------------------------------------------
# Slurm state mapping (plan §3 table)
# ---------------------------------------------------------------------------


class TestStateMapping:
    def test_normalize_strips_cancelled_annotation(self):
        assert normalize_slurm_state("CANCELLED by 12345") == "CANCELLED"
        assert normalize_slurm_state("cancelled+") == "CANCELLED"

    @pytest.mark.parametrize(
        "state,expected",
        [
            ("PENDING", RunStatus.running),
            ("CONFIGURING", RunStatus.running),
            ("RUNNING", RunStatus.running),
            ("SUSPENDED", RunStatus.paused),
            ("COMPLETED", RunStatus.completed),
            ("FAILED", RunStatus.failed),
            ("TIMEOUT", RunStatus.failed),
            ("OUT_OF_MEMORY", RunStatus.failed),
            ("NODE_FAIL", RunStatus.failed),
            ("CANCELLED by 7", RunStatus.cancelled),
        ],
    )
    def test_maps_states(self, state, expected):
        assert map_slurm_state(state) == expected

    def test_unknown_state_defaults_to_running(self):
        assert map_slurm_state("SOME_NEW_STATE") == RunStatus.running

    def test_completed_but_not_landed_stays_running(self):
        # §3 invariant: completion means LANDED, not Slurm-exited.
        assert map_slurm_state("COMPLETED", landed=False) == RunStatus.running
        assert map_slurm_state("COMPLETED", landed=True) == RunStatus.completed

    def test_failed_is_terminal_regardless_of_landing(self):
        assert map_slurm_state("FAILED", landed=False) == RunStatus.failed

    def test_terminal_detection(self):
        assert is_terminal_slurm_state("COMPLETED")
        assert is_terminal_slurm_state("FAILED")
        assert is_terminal_slurm_state("CANCELLED")
        assert not is_terminal_slurm_state("RUNNING")
        assert not is_terminal_slurm_state("PENDING")


# ---------------------------------------------------------------------------
# Array directive (plan §3 — sparse resubmission)
# ---------------------------------------------------------------------------


class TestArrayDirective:
    def test_contiguous_range(self):
        assert build_array_directive([0, 1, 2, 3]) == "--array=0-3"

    def test_single_index(self):
        assert build_array_directive([5]) == "--array=5"

    def test_sparse_indices_compress_into_ranges(self):
        # A re-submit after partial failure passes only the missing indices.
        assert build_array_directive([0, 2, 3, 4, 7]) == "--array=0,2-4,7"

    def test_throttle_appended(self):
        assert build_array_directive([0, 1, 2, 3], throttle=2) == "--array=0-3%2"

    def test_unsorted_and_duplicate_indices_normalized(self):
        assert build_array_directive([3, 1, 0, 2, 2]) == "--array=0-3"

    def test_empty_raises(self):
        with pytest.raises(HpcConfigError):
            build_array_directive([])

    def test_negative_index_raises(self):
        with pytest.raises(HpcConfigError):
            build_array_directive([-1, 0])


# ---------------------------------------------------------------------------
# Run-spec builder + submitter fake
# ---------------------------------------------------------------------------


def _manifest(run_id="run-7", n=3):
    return build_bundle_manifest(
        workflow_id="wf-1",
        workflow_name="Transcribe",
        input_files=[f"/inputs/{i}.pdf" for i in range(n)],
        library_path="/lib.fichero",
        run_id=run_id,
    )


class TestRemoteRunSpec:
    def test_spec_folds_array_and_account_into_script(self):
        spec = build_remote_run_spec(
            cluster=_cluster(),
            manifest=_manifest(n=3),
            input_indices=[0, 1, 2],
            throttle=2,
        )
        assert spec.array_directive == "--array=0-2%2"
        assert spec.remote_workdir == "/scratch/researcher/fichero/runs/run-7"
        assert "#SBATCH --array=0-2%2" in spec.sbatch_script
        assert "#SBATCH --account=def-lab" in spec.sbatch_script
        assert "#SBATCH --partition=gpu" in spec.sbatch_script
        assert "${SLURM_ARRAY_TASK_ID}" in spec.sbatch_script

    def test_spec_validates_cluster(self):
        with pytest.raises(HpcConfigError):
            build_remote_run_spec(
                cluster=_cluster(remote_base_dir="relative"),
                manifest=_manifest(),
                input_indices=[0],
            )

    def test_dry_run_submitter_records_and_scripts_states(self):
        sub = DryRunSubmitter(
            job_id="99",
            state_sequence=[{"99_0": "PENDING"}, {"99_0": "RUNNING"}, {"99_0": "COMPLETED"}],
        )
        spec = build_remote_run_spec(
            cluster=_cluster(), manifest=_manifest(), input_indices=[0, 1, 2]
        )
        res = sub.submit(spec)
        assert res.job_id == "99"
        assert res.remote_workdir == spec.remote_workdir
        assert sub.submitted == [spec]
        # Poll sequence advances then repeats the last.
        assert sub.poll("99") == {"99_0": "PENDING"}
        assert sub.poll("99") == {"99_0": "RUNNING"}
        assert sub.poll("99") == {"99_0": "COMPLETED"}
        assert sub.poll("99") == {"99_0": "COMPLETED"}
        sub.cancel("99")
        assert sub.cancelled == ["99"]


# ---------------------------------------------------------------------------
# SSH command construction (pure — nothing executes)
# ---------------------------------------------------------------------------


class TestSshCommands:
    def test_ssh_command_uses_host_alias_and_port(self):
        cmd = build_ssh_command(_cluster(ssh_port=2222), ["echo", "hi there"])
        assert cmd[0] == "ssh"
        assert "researcher@acenet" in cmd
        assert "2222" in cmd
        # The remote command is a single quoted string arg.
        assert cmd[-1] == "echo 'hi there'"

    def test_sinfo_probe_targets_partition(self):
        cmd = build_sinfo_probe_command(_cluster())
        assert cmd[0] == "ssh"
        assert "sinfo -p gpu" in cmd[-1]
