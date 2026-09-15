import unittest
from pathlib import Path


class HumanInputContractTests(unittest.TestCase):
    def test_skill_documents_host_specific_user_input_tools(self):
        skill = (Path(__file__).parents[1] / "src" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Hermes", skill)
        self.assertIn("ask_user", skill)
        self.assertIn("Codex", skill)


if __name__ == "__main__":
    unittest.main()
