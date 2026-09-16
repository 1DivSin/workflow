import ast
import unittest
from pathlib import Path


class HostAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[1] / "src" / "fusion_flow" / "host_adapter.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_no_developer_machine_paths_are_injected(self):
        self.assertNotIn("/public/home/sychen", self.source)

    def test_host_config_uses_explicit_app_server_command(self):
        self.assertIn("CODEX_APP_SERVER_COMMAND", self.source)
        self.assertIn("HERMES_ACP_COMMAND", self.source)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "host_config" for node in self.tree.body))



if __name__ == "__main__":
    unittest.main()
