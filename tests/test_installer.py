import json
import subprocess
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.detect import detect_host
from installer.installer import install


class InstallerTests(unittest.TestCase):
    def test_detects_codex_from_app_server_command(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            old = os.environ.copy()
            try:
                os.environ["CODEX_HOME"] = str(home / ".codex")
                os.environ["CODEX_APP_SERVER_COMMAND"] = "codex app-server --stdio"
                os.environ["PSI_WORKFLOW_HOST"] = "codex"
                host = detect_host(home=home, which=lambda _name: None)
            finally:
                os.environ.clear()
                os.environ.update(old)
        self.assertEqual(host["name"], "codex")
        self.assertTrue(host["available"])

    def test_install_copies_skill_and_records_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("---\nname: workflow\n---\n", encoding="utf-8")
            host = {
                "name": "codex",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
            }
            target = install(source, host=host)
            self.assertTrue((target / "src" / "SKILL.md").is_file())
            self.assertTrue((root / "skills" / "workflow" / "SKILL.md").is_file())
            state = json.loads((root / "state" / "genuineknowledge-method.json").read_text())
            self.assertEqual(Path(state["skill_dir"]), root / "skills" / "workflow")

    def test_openclaw_registration_is_explicit_and_records_plugin(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("skill", encoding="utf-8")
            (source / "plugins" / "openclaw-workflow").mkdir(parents=True)
            (source / "plugins" / "openclaw-workflow" / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            host = {
                "name": "openclaw",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
                "executable": "openclaw",
            }
            calls = []
            def runner(command, **_kwargs):
                calls.append(command)
            target = install(source, host=host, register_plugin=True, runner=runner)
            self.assertTrue((target / "plugins" / "openclaw-workflow" / "openclaw.plugin.json").is_file())
            self.assertEqual(calls[0][0:3], ("openclaw", "plugins", "install"))
            state = json.loads((root / "state" / "genuineknowledge-method.json").read_text())
            self.assertEqual(Path(state["plugin_dir"]), target / "plugins" / "openclaw-workflow")


if __name__ == "__main__":
    unittest.main()
