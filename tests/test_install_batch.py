import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer import cli
from installer.detect import detect_hosts


class BatchInstallTests(unittest.TestCase):
    def test_detect_hosts_returns_all_hosts_in_stable_order(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            for name in ("codex", "openclaw", "hermes"):
                (home / f".{name}").mkdir()
            hosts = detect_hosts(home=home, environ={}, which=lambda _: None)
        self.assertEqual([host["name"] for host in hosts], ["codex", "openclaw", "hermes"])

    def test_repeated_host_options_install_each_host_and_continue_after_failure(self):
        hosts = [
            {"name": "codex", "available": True},
            {"name": "hermes", "available": True},
        ]
        results = [
            {"host": "codex", "ok": True, "target": "codex-target"},
            {"host": "hermes", "ok": False, "error": "failed"},
        ]
        with patch("installer.cli.detect_host", side_effect=hosts), patch(
            "installer.cli.install_many", return_value=results
        ) as install_many:
            status = cli.main(["installer", ".", "--host", "codex", "--host", "hermes"])
        self.assertEqual(status, 1)
        self.assertEqual(install_many.call_args.args[1], hosts)

    def test_all_uses_batch_installer_and_auto_registers_openclaw(self):
        hosts = [{"name": "codex", "available": True}, {"name": "openclaw", "available": True}]
        results = [{"host": "codex", "ok": True, "target": "codex"}, {"host": "openclaw", "ok": True, "target": "openclaw"}]
        with patch("installer.cli.detect_hosts", return_value=hosts), patch(
            "installer.cli.install_many", return_value=results
        ) as install_many:
            status = cli.main(["installer", ".", "--all"])
        self.assertEqual(status, 0)
        self.assertTrue(install_many.call_args.kwargs["register_plugin"])

    def test_install_many_creates_independent_host_assets_and_state(self):
        from installer.installer import install_many

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("---\nname: workflow\n---\n", encoding="utf-8")
            hosts = [
                {
                    "name": "codex",
                    "home": str(root / "codex-home"),
                    "workspace": str(root / "codex-workspace"),
                    "state_dir": str(root / "codex-state"),
                    "tools_dir": str(root / "codex-tools"),
                    "skills_dir": str(root / "codex-skills"),
                },
                {
                    "name": "hermes",
                    "home": str(root / "hermes-home"),
                    "workspace": str(root / "hermes-workspace"),
                    "state_dir": str(root / "hermes-state"),
                    "tools_dir": str(root / "hermes-tools"),
                    "skills_dir": str(root / "hermes-skills"),
                },
            ]
            results = install_many(source, hosts)

            self.assertEqual([result["host"] for result in results], ["codex", "hermes"])
            self.assertTrue(all(result["ok"] for result in results))
            self.assertTrue((root / "codex-tools" / "genuineknowledge-method").is_dir())
            self.assertTrue((root / "hermes-tools" / "genuineknowledge-method").is_dir())
            self.assertTrue((root / "codex-state" / "genuineknowledge-method.json").is_file())
            self.assertTrue((root / "hermes-state" / "genuineknowledge-method.json").is_file())
            self.assertIn('PSI_WORKFLOW_HOST = "codex"', (root / "codex-home" / "config.toml").read_text())
            self.assertIn('PSI_WORKFLOW_HOST: "hermes"', (root / "hermes-home" / "config.yaml").read_text())

    def test_all_and_host_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            cli.main(["installer", ".", "--all", "--host", "codex"])


if __name__ == "__main__":
    unittest.main()
