import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import configure_hermes_mcp


class HermesInstallTests(unittest.TestCase):
    def test_adds_managed_mcp_server_without_touching_existing_config(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.yaml"
            config.write_text("mcp_servers:\n  other:\n    command: other\n", encoding="utf-8")
            configure_hermes_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            text = config.read_text(encoding="utf-8")
            self.assertIn("  other:\n    command: other", text)
            self.assertIn("  fusion_flow:", text)
            self.assertIn("fusion_flow.mcp_server", text)
            self.assertEqual(text.count("fusion_flow:"), 1)

    def test_is_idempotent_and_creates_config(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "nested" / "config.yaml"
            configure_hermes_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            first = config.read_text(encoding="utf-8")
            configure_hermes_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            self.assertEqual(config.read_text(encoding="utf-8"), first)

    def test_preserves_existing_user_server_configuration(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.yaml"
            original = (
                "mcp_servers:\n"
                "  fusion_flow:\n"
                "    command: /user/selected/python\n"
                "    args: [custom-server]\n"
            )
            config.write_text(original, encoding="utf-8")
            configure_hermes_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            self.assertEqual(config.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
