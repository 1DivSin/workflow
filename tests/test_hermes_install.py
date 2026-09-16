import tempfile
import unittest
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import configure_hermes_mcp


class HermesInstallTests(unittest.TestCase):
    def test_server_is_inserted_under_mcp_servers_before_later_sections(self):
        originals = [
            'mcp_servers:\n  other:\n    command: other\ndisplay:\n  mode: compact\n',
            'mcp_servers:\n    other: {command: other}\n# display comment\ndisplay:\n    fusion_flow: user-data\n',
            'mcp_servers: {} # empty mapping\ndisplay: {mode: compact}\n',
            'mcp_servers: # no servers yet\ndisplay: {mode: compact}\n',
        ]
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / 'config.yaml'
            for original in originals:
                with self.subTest(original=original):
                    config.write_text(original, encoding='utf-8')
                    configure_hermes_mcp(config, Path(raw)/'runtime', raw)
                    result = config.read_text(encoding='utf-8')
                    parsed, before = yaml.safe_load(result), yaml.safe_load(original)
                    self.assertEqual(parsed['display'], before['display'])
                    servers = parsed['mcp_servers']
                    self.assertEqual(servers['fusion_flow']['args'], ['-m','fusion_flow.mcp_server'])
                    for key, value in (before['mcp_servers'] or {}).items():
                        self.assertEqual(servers[key], value)
                    configure_hermes_mcp(config, Path(raw)/'runtime', raw)
                    self.assertEqual(config.read_text(encoding='utf-8'), result)

    def test_invalid_config_is_unchanged(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw)/'config.yaml'
            for original in ('mcp_servers: [unterminated\n', 'mcp_servers: [wrong, type]\n'):
                config.write_text(original, encoding='utf-8')
                with self.assertRaises((ValueError, yaml.YAMLError)):
                    configure_hermes_mcp(config, raw, raw)
                self.assertEqual(config.read_text(encoding='utf-8'), original)

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
