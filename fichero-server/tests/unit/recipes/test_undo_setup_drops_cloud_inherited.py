"""An undo of a setup save (or of Allow Cloud) replays the before-state, which read_project_setup reports with the
response-only cloud_inherited beside the answers (## 1101). The replay must drop it, or ProjectSetup refuses it (422)."""
from fichero_server.api.routes.system.recipes import ProjectSetup, _invert_allow_cloud, _invert_save_setup


def test_both_setup_undos_replay_a_setup_the_action_accepts():
    before = {"answers": {"languages": ["es"]}, "recipe": None, "cloud_inherited": True}
    for invert in (_invert_save_setup, _invert_allow_cloud):
        name, params = invert(before, None, None)
        assert name == "project.save_setup" and "cloud_inherited" not in params
        ProjectSetup(**params)  # accepted: no extra field
    assert _invert_save_setup(None, None, None)[1] == {"answers": None, "recipe": None}
