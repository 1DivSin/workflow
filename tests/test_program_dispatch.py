import ast
import unittest
from pathlib import Path


class ProgramDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[1] / "src" / "run_flow.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_openclaw_program_helper_is_defined_once(self):
        names = [node for node in self.tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_complete_program_step_openclaw"]
        self.assertEqual(len(names), 1)

    def test_program_dispatch_selects_openclaw_before_hermes(self):
        node = next(node for node in self.tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_complete_program_step")
        calls = [
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        ]
        self.assertIn("_complete_program_step_openclaw", calls)
        self.assertIn("_complete_program_step_hermes", calls)
        self.assertLess(
            ast.unparse(node).index("_complete_program_step_openclaw"),
            ast.unparse(node).index("_complete_program_step_hermes"),
        )


if __name__ == "__main__":
    unittest.main()
