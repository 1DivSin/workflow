import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import install


class OpenClawPluginRuntimeConfigTests(unittest.TestCase):
    def test_source_install_records_uv_backed_runtime_commands(self):
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

            fake_uv = "/opt/bin/uv"
            with patch(
                "installer.installer.shutil.which",
                side_effect=lambda name: fake_uv if name == "uv" else None,
            ):
                target = install(source, host=host)
            runtime = json.loads(
                (target / "plugins" / "openclaw-workflow" / "runtime.json").read_text(
                    encoding="utf-8"
                )
            )

            source_path = str(source.resolve())
            expected_uv = str(Path(fake_uv).resolve())
            self.assertEqual(
                runtime["mcpCommand"],
                [expected_uv, "run", "--project", source_path, "dynamic-workflow-mcp"],
            )
            self.assertEqual(
                runtime["toolCommand"],
                [expected_uv, "run", "--project", source_path, "dynamic-workflow-tool"],
            )
            self.assertNotIn("python", runtime)
            self.assertNotIn("runtimeRoot", runtime)
            self.assertEqual(runtime["workspace"], str(workspace.resolve()))


if __name__ == "__main__":
    unittest.main()
