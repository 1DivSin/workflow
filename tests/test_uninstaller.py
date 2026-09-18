import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.uninstaller import uninstall


class UninstallerTests(unittest.TestCase):
    def test_codex_removes_runtime_skill_mcp_block_and_state(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "tools" / "genuineknowledge-method"
            skill = root / "skills" / "workflow"
            target.mkdir(parents=True)
            skill.mkdir(parents=True)
            (target / "marker").write_text("runtime", encoding="utf-8")
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            home = root / ".codex"
            home.mkdir()
            config = home / "config.toml"
            config.write_text(
                "[profiles.default]\nmodel = \"gpt\"\n\n"
                "# BEGIN dynamic-workflow\n"
                "[mcp_servers.fusion_flow]\ncommand = \"python\"\n"
                "[mcp_servers.fusion_flow.env]\nPSI_WORKFLOW_HOST = \"codex\"\n"
                "# END dynamic-workflow\n",
                encoding="utf-8",
            )
            state_dir = root / "state"
            state_dir.mkdir()
            state = state_dir / "genuineknowledge-method.json"
            state.write_text(
                json.dumps({"target": str(target), "skill_dir": str(skill), "host": "codex"}),
                encoding="utf-8",
            )
            host = {
                "name": "codex",
                "home": str(home),
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(state_dir),
            }

            uninstall(host=host, purge_state=True)

            self.assertFalse(target.exists())
            self.assertFalse(skill.exists())
            self.assertFalse(state.exists())
            config_text = config.read_text(encoding="utf-8")
            self.assertIn("[profiles.default]", config_text)
            self.assertNotIn("fusion_flow", config_text)

    def test_openclaw_unregisters_registered_plugin(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "tools" / "genuineknowledge-method"
            plugin = target / "plugins" / "openclaw-workflow"
            plugin.mkdir(parents=True)
            skill = root / "skills" / "workflow"
            skill.mkdir(parents=True)
            state_dir = root / "state"
            state_dir.mkdir()
            (state_dir / "genuineknowledge-method.json").write_text(
                json.dumps(
                    {
                        "target": str(target),
                        "skill_dir": str(skill),
                        "plugin_dir": str(plugin),
                        "plugin_registered": True,
                        "host": "openclaw",
                    }
                ),
                encoding="utf-8",
            )
            calls = []
            host = {
                "name": "openclaw",
                "home": str(root / ".openclaw"),
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(state_dir),
                "executable": "openclaw",
            }

            uninstall(host=host, purge_state=True, runner=lambda command, **_: calls.append(command))

            self.assertEqual(calls[0][:3], ("openclaw", "plugins", "uninstall"))
            self.assertFalse(target.exists())
            self.assertFalse(skill.exists())


if __name__ == "__main__":
    unittest.main()
