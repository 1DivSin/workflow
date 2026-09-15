import json
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


if __name__ == "__main__":
    unittest.main()
