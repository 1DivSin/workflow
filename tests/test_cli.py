import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer import cli


class CliTests(unittest.TestCase):
    def test_register_plugin_targets_openclaw(self):
        with patch.object(
            sys, "argv", ["method-installer", "installer", ".", "--register-plugin"]
        ), patch("installer.cli.install", return_value=Path("installed")) as install_mock:
            cli.main()
        self.assertEqual(install_mock.call_args.kwargs["target_host"], "openclaw")
        self.assertTrue(install_mock.call_args.kwargs["register_plugin"])

    def test_explicit_non_openclaw_host_conflicts_with_register_plugin(self):
        with patch.object(
            sys,
            "argv",
            ["method-installer", "installer", ".", "--host", "codex", "--register-plugin"],
        ), patch("installer.cli.install") as install_mock:
            with self.assertRaises(SystemExit):
                cli.main()
        install_mock.assert_not_called()

    def test_install_prints_hermes_progress_and_doctor_hint(self):
        workspace = Path("workspace").resolve()
        home = Path("hermes-home").resolve()
        host = {
            "name": "hermes",
            "home": str(home),
            "workspace": str(workspace),
            "state_dir": str(home / "state"),
            "tools_dir": str(home / "tools"),
            "skills_dir": str(home / "skills"),
            "command": (),
            "executable": "hermes",
            "available": True,
        }
        target = (home / "tools" / "genuineknowledge-method").resolve()
        output = StringIO()

        with patch("installer.cli.detect_host", return_value=host), patch(
            "installer.cli.install", return_value=target
        ), redirect_stdout(output):
            cli.main(["install", ".", "--host", "hermes", "--workspace", str(workspace)])

        text = output.getvalue()
        self.assertIn(f"[1/4] Runtime assets installed: {target}", text)
        self.assertIn(f"[2/4] Workflow skill installed: {home / 'skills' / 'workflow'}", text)
        self.assertIn(f"[3/4] Hermes MCP configured: {home / 'config.yaml'}", text)
        self.assertIn(
            f"[4/4] Installation state written: {home / 'state' / 'genuineknowledge-method.json'}",
            text,
        )
        self.assertIn("Installation complete.", text)
        self.assertIn("uv run dynamic-workflow doctor --host hermes", text)


if __name__ == "__main__":
    unittest.main()
