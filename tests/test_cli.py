import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
