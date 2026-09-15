import tempfile
import unittest
from pathlib import Path

from install_workflow import Host, choose_host, detect_hosts, install_codex, install_host


class InstallWorkflowTests(unittest.TestCase):
    def test_detect_hosts_reports_codex_from_native_directories(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / ".codex").mkdir()
            hosts = detect_hosts(home=home, which=lambda _name: None)
        self.assertEqual([host.name for host in hosts], ["Codex"])
        self.assertTrue(hosts[0].available)

    def test_choose_host_rejects_invalid_input_then_accepts_number(self):
        hosts = detect_hosts(home=Path("C:/missing"), which=lambda _name: "x")
        messages = []
        answers = iter(["9", "1"])
        selected = choose_host(hosts, input_fn=lambda _prompt: next(answers), output_fn=messages.append)
        self.assertEqual(selected.name, hosts[0].name)
        self.assertTrue(any("Invalid selection" in message for message in messages))

    def test_install_codex_copies_workflow_and_skill(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            skill = source / "skills" / "dynamic-workflow"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: dynamic-workflow\n---\n", encoding="utf-8")
            result = install_codex(source, root / "home")
            self.assertTrue(result.ok)
            self.assertTrue((root / "home" / ".codex" / "dynamic-workflow" / "skills" / "dynamic-workflow" / "SKILL.md").exists())
            self.assertTrue(result.target.exists())

    def test_install_codex_reports_missing_source(self):
        with tempfile.TemporaryDirectory() as raw:
            result = install_codex(Path(raw) / "missing", Path(raw) / "home")
        self.assertFalse(result.ok)
        self.assertIn("source", result.error.lower())

    def test_install_host_copies_skill_for_claude(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source").mkdir()
            (root / "source" / "SKILL.md").write_text("skill", encoding="utf-8")
            host = Host("Claude", "claude", (), True)
            result = install_host(host, root / "source", root / "home")
            self.assertTrue(result.ok)
            self.assertTrue((root / "home" / ".claude" / "skills" / "dynamic-workflow" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
