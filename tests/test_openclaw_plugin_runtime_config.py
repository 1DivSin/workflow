import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import install


class OpenClawPluginRuntimeConfigTests(unittest.TestCase):
    def test_install_records_current_python_for_plugin_runtime(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            workspace = root / "workspace"
            workspace.mkdir()
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("skill", encoding="utf-8")
            plugin = source / "plugins" / "openclaw-workflow"
            plugin.mkdir(parents=True)
            (plugin / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            host = {
                "name": "openclaw",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
                "workspace": str(workspace),
            }

            target = install(source, host=host)
            runtime = json.loads(
                (target / "plugins" / "openclaw-workflow" / "runtime.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(runtime["python"], sys.executable)
            self.assertEqual(runtime["runtimeRoot"], str(target))
            self.assertEqual(runtime["workspace"], str(workspace.resolve()))


if __name__ == "__main__":
    unittest.main()
