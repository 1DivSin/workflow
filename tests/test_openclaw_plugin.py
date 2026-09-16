import json
import unittest
from pathlib import Path


class OpenClawPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parents[1] / "plugins" / "openclaw-workflow"

    def test_manifest_declares_all_workflow_tools(self):
        manifest = json.loads((self.root / "openclaw.plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["contracts"]["tools"],
            ["run_flow", "run_flow_resume", "flow_manage"],
        )

    def test_entry_delegates_to_runtime_bridge(self):
        entry = (self.root / "index.js").read_text(encoding="utf-8")
        self.assertEqual(entry.count("api.registerTool"), 3)
        self.assertEqual(entry.count('runWorkflow("'), 3)


if __name__ == "__main__":
    unittest.main()
