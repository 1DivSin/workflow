import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer import cli
from installer.detect import detect_host
from installer.installer import _openclaw_cli_command


class InstallerHostSelectionTests(unittest.TestCase):
    def test_explicit_target_selects_openclaw_when_codex_is_also_available(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)

            def which(name):
                return {"codex": "codex", "openclaw": "openclaw"}.get(name)

            host = detect_host(target="openclaw", home=home, environ={}, which=which)
        self.assertEqual(host["name"], "openclaw")
        self.assertEqual(host["executable"], "openclaw")

    def test_wrapped_openclaw_command_is_kept_separate_from_management_executable(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            host = detect_host(
                target="openclaw",
                home=home,
                environ={"OPENCLAW_COMMAND": "uv run openclaw agent"},
                which=lambda _name: None,
            )
        self.assertEqual(host["command"], ("uv", "run", "openclaw", "agent"))
        self.assertIsNone(host["executable"])

    def test_register_plugin_selects_openclaw_before_detection(self):
        detected = {
            "name": "openclaw",
            "available": True,
            "home": "/tmp/openclaw",
            "workspace": "/tmp/workspace",
            "state_dir": "/tmp/openclaw/state",
            "tools_dir": "/tmp/openclaw/tools",
            "skills_dir": "/tmp/openclaw/skills",
            "executable": "openclaw",
            "command": (),
        }
        with patch("installer.cli.detect_host", return_value=detected) as detect_mock, patch(
            "installer.cli.install", return_value=Path("installed")
        ) as install_mock:
            cli.main(["installer", ".", "--register-plugin"])
        self.assertEqual(detect_mock.call_args.kwargs["target"], "openclaw")
        self.assertTrue(install_mock.call_args.kwargs["register_plugin"])
        self.assertEqual(install_mock.call_args.kwargs["host"]["name"], "openclaw")

    def test_windows_openclaw_management_commands_use_comspec(self):
        with patch("installer.installer.sys.platform", "win32"), patch.dict(
            os.environ, {"COMSPEC": r"C:\\Windows\\System32\\cmd.exe"}, clear=False
        ):
            for arguments in (
                ("plugins", "install", "--link", r"C:\\plugin", "--force"),
                ("plugins", "enable", "genuineknowledge-workflow"),
                ("plugins", "inspect", "genuineknowledge-workflow", "--runtime", "--json"),
            ):
                with self.subTest(arguments=arguments):
                    command = _openclaw_cli_command(r"C:\\npm\\openclaw.cmd", *arguments)
                    self.assertEqual(
                        command[:4],
                        (r"C:\\Windows\\System32\\cmd.exe", "/d", "/s", "/c"),
                    )
                    self.assertIn("openclaw.cmd", command[4])
                    self.assertIn("plugins", command[4])


if __name__ == "__main__":
    unittest.main()
