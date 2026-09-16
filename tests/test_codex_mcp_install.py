import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import configure_codex_mcp


class CodexMcpInstallTests(unittest.TestCase):
    def test_configure_codex_mcp_is_idempotent_and_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            config.write_text('[profiles.default]\nmodel = "gpt-5"\n', encoding="utf-8")
            configure_codex_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            first = config.read_text(encoding="utf-8")
            configure_codex_mcp(config, Path(raw) / "runtime", Path(raw) / "workspace")
            self.assertEqual(config.read_text(encoding="utf-8"), first)
            self.assertIn("[profiles.default]", first)
            self.assertIn("[mcp_servers.fusion_flow]", first)
            self.assertEqual(first.count("[mcp_servers.fusion_flow]"), 1)


if __name__ == "__main__":
    unittest.main()
