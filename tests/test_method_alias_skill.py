import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "src" / "SKILL.md"


class MethodAliasSkillTests(unittest.TestCase):
    def test_method_is_exposed_as_workflow_alias(self):
        skill = " ".join(SKILL.read_text(encoding="utf-8").split()).lower()

        self.assertIn("method / method skill is the user-facing alias", skill)
        self.assertIn("there is no separate method skill", skill)
        self.assertIn("用 method 解决这个问题", skill)
        self.assertIn("method 一下这个任务", skill)
        self.assertIn("这个交给 method", skill)
        self.assertIn("use method for this", skill)
        self.assertIn("what method should i use?", skill)

    def test_method_alias_keeps_workflow_authoring_and_execution_path(self):
        skill = " ".join(SKILL.read_text(encoding="utf-8").split()).lower()

        self.assertIn("treat method as workflow", skill)
        self.assertIn("enter the same authoring mode", skill)
        self.assertIn("create the g4 workflow", skill)
        self.assertIn("run it unless the user explicitly asks", skill)


if __name__ == "__main__":
    unittest.main()
