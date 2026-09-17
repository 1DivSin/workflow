import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class HostPathTests(unittest.TestCase):
    def test_flow_manage_uses_psi_workspace(self):
        from flow_manage import _flows_dir

        with tempfile.TemporaryDirectory() as workspace, patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "", "PSI_WORKFLOW_WORKSPACE": workspace},
            clear=False,
        ):
            self.assertEqual(Path(str(_flows_dir())).resolve(), (Path(workspace) / "flows").resolve())

    def test_host_source_is_only_used_when_configured(self):
        from fusion_flow.host_adapter import host_config

        with tempfile.TemporaryDirectory() as workspace, patch.dict(
            os.environ,
            {
                "PSI_WORKFLOW_HOST": "codex",
                "PSI_WORKFLOW_WORKSPACE": workspace,
                "CODEX_EXECUTABLE": "codex.js",
                "CODEX_SOURCE": "",
            },
            clear=False,
        ):
            with patch("fusion_flow.host_adapter.shutil.which", return_value=None):
                config = host_config(workspace)
            self.assertEqual(config.workspace, Path(workspace).resolve())
            self.assertEqual(config.executable, "codex.js")

    def test_workspace_override_expands_user_path(self):
        from fusion_flow.host_adapter import workspace_dir

        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "", "PSI_WORKFLOW_WORKSPACE": "~"},
            clear=False,
        ):
            self.assertEqual(workspace_dir("."), Path.home().resolve())

        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "", "PSI_WORKFLOW_WORKSPACE": "relative-workspace"},
            clear=False,
        ):
            self.assertEqual(workspace_dir("."), (Path.cwd() / "relative-workspace").resolve())

    def test_host_adapter_has_no_machine_specific_source_root(self):
        from fusion_flow import host_adapter

        self.assertNotIn("/public/home/sychen", Path(host_adapter.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
