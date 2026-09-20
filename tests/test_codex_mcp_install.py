import tempfile
import tomllib
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.installer import configure_codex_mcp


class CodexMcpInstallTests(unittest.TestCase):
    def test_user_owned_server_is_preserved_without_duplicate_tables(self):
        originals = [
            '# custom server\n[mcp_servers.fusion_flow]\ncommand = "my-server"\n',
            'mcp_servers = {fusion_flow = {command = "my-server"}}\n',
        ]
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            for original in originals:
                with self.subTest(original=original):
                    config.write_text(original, encoding="utf-8")
                    configure_codex_mcp(config, ("/opt/dynamic-workflow-mcp",), Path(raw))
                    result = config.read_text(encoding="utf-8")
                    self.assertEqual(tomllib.loads(result), tomllib.loads(original))
                    self.assertEqual(result, original)

    def test_user_owned_server_with_different_host_is_rejected(self):
        original = (
            "[mcp_servers.fusion_flow]\n"
            'command = "hermes-workflow"\n'
            '[mcp_servers.fusion_flow.env]\n'
            'PSI_WORKFLOW_HOST = "hermes"\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            config.write_text(original, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "host.*hermes.*codex"):
                configure_codex_mcp(config, ("dynamic-workflow-mcp",), raw)
            self.assertEqual(config.read_text(encoding="utf-8"), original)
    def test_inline_mcp_servers_can_receive_managed_server_and_update_it(self):
        originals = [
            "mcp_servers = {}\n",
            'mcp_servers = {other = {command = "other", args = ["--flag"]}}\n',
        ]
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            for original in originals:
                with self.subTest(original=original):
                    config.write_text(original, encoding="utf-8")
                    configure_codex_mcp(
                        config,
                        ("/opt/old/dynamic-workflow-mcp", "--stdio"),
                        raw,
                    )
                    first = config.read_text(encoding="utf-8")
                    parsed = tomllib.loads(first)
                    self.assertIn("fusion_flow", parsed["mcp_servers"])
                    before = tomllib.loads(original)["mcp_servers"]
                    for key, value in before.items():
                        self.assertEqual(parsed["mcp_servers"][key], value)
                    self.assertIn("# dynamic-workflow managed fusion_flow", first)

                    configure_codex_mcp(
                        config,
                        ("/opt/new/dynamic-workflow-mcp",),
                        raw,
                    )
                    updated = tomllib.loads(config.read_text(encoding="utf-8"))
                    server = updated["mcp_servers"]["fusion_flow"]
                    self.assertEqual(server["command"], "/opt/new/dynamic-workflow-mcp")
                    self.assertEqual(server["args"], [])
                    self.assertEqual(server["tool_timeout_sec"], 900)
                    self.assertNotIn("PYTHONPATH", server["env"])

    def test_invalid_config_and_incomplete_managed_block_are_not_written(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            for original in ('[bad\n', '# BEGIN dynamic-workflow\nmodel="custom"\n'):
                with self.subTest(original=original):
                    config.write_text(original, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        configure_codex_mcp(config, ("dynamic-workflow-mcp",), raw)
                    self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_managed_update_preserves_later_tables(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            configure_codex_mcp(config, ("/old/mcp",), raw)
            with config.open("a", encoding="utf-8") as stream:
                stream.write('\n# another integration\n[mcp_servers.other]\ncommand="other"\n')
            configure_codex_mcp(config, ("/new/mcp", "--stdio"), raw)
            result = config.read_text(encoding="utf-8")
            parsed = tomllib.loads(result)
            self.assertEqual(parsed["mcp_servers"]["other"]["command"], "other")
            server = parsed["mcp_servers"]["fusion_flow"]
            self.assertEqual(server["command"], "/new/mcp")
            self.assertEqual(server["args"], ["--stdio"])
            self.assertEqual(server["tool_timeout_sec"], 900)
            self.assertIn("# another integration", result)

    def test_configure_codex_mcp_is_idempotent_and_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.toml"
            config.write_text('[profiles.default]\nmodel = "gpt-5"\n', encoding="utf-8")
            command = ("/opt/dynamic-workflow-mcp",)
            configure_codex_mcp(config, command, Path(raw) / "workspace")
            first = config.read_text(encoding="utf-8")
            configure_codex_mcp(config, command, Path(raw) / "workspace")
            self.assertEqual(config.read_text(encoding="utf-8"), first)
            self.assertIn("[profiles.default]", first)
            self.assertIn("[mcp_servers.fusion_flow]", first)
            self.assertEqual(first.count("[mcp_servers.fusion_flow]"), 1)
            parsed = tomllib.loads(first)
            server = parsed["mcp_servers"]["fusion_flow"]
            self.assertEqual(server["command"], command[0])
            self.assertEqual(server["tool_timeout_sec"], 900)
            self.assertNotIn("PYTHONPATH", server["env"])


if __name__ == "__main__":
    unittest.main()
