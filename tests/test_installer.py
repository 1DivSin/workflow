import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from installer.detect import detect_host
from installer.installer import (
    _openclaw_plugin_command,
    _resolve_runtime_commands,
    install,
)


MCP_COMMAND = ("/opt/dynamic-workflow-mcp",)
TOOL_COMMAND = ("/opt/dynamic-workflow-tool",)


class InstallerTests(unittest.TestCase):
    def test_detects_codex_from_app_server_command(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            env = {
                "CODEX_HOME": str(home / ".codex"),
                "CODEX_APP_SERVER_COMMAND": "codex app-server --stdio",
                "PSI_WORKFLOW_HOST": "codex",
            }
            host = detect_host(home=home, environ=env, which=lambda _name: None)
        self.assertEqual(host["name"], "codex")
        self.assertTrue(host["available"])
        self.assertEqual(host["command"], ("codex", "app-server", "--stdio"))
        self.assertEqual(host["executable"], "codex")

    def test_detects_direct_openclaw_command_as_management_executable(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            env = {
                "OPENCLAW_COMMAND": "openclaw agent",
                "PSI_WORKFLOW_HOST": "openclaw",
            }
            host = detect_host(home=home, environ=env, which=lambda _name: None)
        self.assertEqual(host["name"], "openclaw")
        self.assertTrue(host["available"])
        self.assertEqual(host["command"], ("openclaw", "agent"))
        self.assertEqual(host["executable"], "openclaw")

    def test_wrapped_openclaw_command_is_preserved_but_not_reused_for_plugin_management(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            env = {
                "OPENCLAW_COMMAND": "uv run openclaw agent",
                "PSI_WORKFLOW_HOST": "openclaw",
            }
            host = detect_host(home=home, environ=env, which=lambda _name: None)
        self.assertEqual(host["name"], "openclaw")
        self.assertTrue(host["available"])
        self.assertEqual(host["command"], ("uv", "run", "openclaw", "agent"))
        self.assertIsNone(host["executable"])

    def test_explicit_openclaw_executable_wins_over_wrapped_command(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            env = {
                "OPENCLAW_COMMAND": "uv run openclaw agent",
                "OPENCLAW_EXECUTABLE": "/opt/openclaw/bin/openclaw",
                "PSI_WORKFLOW_HOST": "openclaw",
            }
            host = detect_host(home=home, environ=env, which=lambda _name: None)
        self.assertEqual(host["command"], ("uv", "run", "openclaw", "agent"))
        self.assertEqual(host["executable"], "/opt/openclaw/bin/openclaw")

    def test_explicit_target_selects_openclaw_when_codex_is_also_available(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)

            def which(name):
                return {"codex": "codex", "openclaw": "openclaw"}.get(name)

            host = detect_host(target="openclaw", home=home, environ={}, which=which)
        self.assertEqual(host["name"], "openclaw")
        self.assertEqual(host["command"], ())
        self.assertEqual(host["executable"], "openclaw")

    def test_source_mode_uses_uv_project_commands(self):
        with tempfile.TemporaryDirectory() as raw, patch(
            "installer.installer.shutil.which",
            side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None,
        ):
            source = Path(raw) / "workflow"
            mcp, tool, mode = _resolve_runtime_commands(source)
        self.assertEqual(mode, "source")
        self.assertEqual(
            mcp,
            (
                "/usr/bin/uv",
                "run",
                "--project",
                str(source.resolve()),
                "dynamic-workflow-mcp",
            ),
        )
        self.assertEqual(tool[-1], "dynamic-workflow-tool")

    def test_installed_mode_resolves_console_entrypoints(self):
        with patch(
            "installer.installer._entrypoint_path",
            side_effect=lambda name: f"/tools/bin/{name}",
        ):
            mcp, tool, mode = _resolve_runtime_commands(None)
        self.assertEqual(mode, "installed")
        self.assertEqual(mcp, ("/tools/bin/dynamic-workflow-mcp",))
        self.assertEqual(tool, ("/tools/bin/dynamic-workflow-tool",))

    def test_install_copies_skill_assets_and_records_runtime_commands(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src" / "grammar").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text(
                "---\nname: workflow\n---\n", encoding="utf-8"
            )
            (source / "src" / "grammar" / "FusionFlow.g4").write_text(
                "grammar FusionFlow;", encoding="utf-8"
            )
            host = {
                "name": "codex",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
                "workspace": str(root),
            }
            target = install(
                source,
                host=host,
                mcp_command=MCP_COMMAND,
                tool_command=TOOL_COMMAND,
            )
            self.assertTrue((target / "src" / "SKILL.md").is_file())
            self.assertTrue((root / "skills" / "workflow" / "SKILL.md").is_file())
            state = json.loads(
                (root / "state" / "genuineknowledge-method.json").read_text()
            )
            self.assertEqual(Path(state["skill_dir"]), root / "skills" / "workflow")
            self.assertEqual(state["mcp_command"], list(MCP_COMMAND))
            self.assertEqual(state["tool_command"], list(TOOL_COMMAND))
            self.assertEqual(state["runtime_mode"], "source")

    def test_openclaw_registration_is_explicit_and_records_plugin(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("skill", encoding="utf-8")
            (source / "plugins" / "openclaw-workflow").mkdir(parents=True)
            (source / "plugins" / "openclaw-workflow" / "openclaw.plugin.json").write_text(
                "{}", encoding="utf-8"
            )
            host = {
                "name": "openclaw",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
                "executable": "openclaw",
                "workspace": str(root),
            }
            calls = []

            def runner(command, **_kwargs):
                calls.append(command)

            target = install(
                source,
                host=host,
                register_plugin=True,
                mcp_command=MCP_COMMAND,
                tool_command=TOOL_COMMAND,
                runner=runner,
            )
            plugin = target / "plugins" / "openclaw-workflow"
            self.assertTrue((plugin / "openclaw.plugin.json").is_file())
            self.assertEqual(calls[0][0:3], ("openclaw", "plugins", "install"))
            runtime = json.loads((plugin / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(runtime["mcpCommand"], list(MCP_COMMAND))
            self.assertEqual(runtime["toolCommand"], list(TOOL_COMMAND))
            state = json.loads(
                (root / "state" / "genuineknowledge-method.json").read_text()
            )
            self.assertEqual(Path(state["plugin_dir"]), plugin)
            self.assertTrue(state["plugin_registered"])

    def test_plugin_validation_happens_before_filesystem_mutation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("skill", encoding="utf-8")
            host = {
                "name": "openclaw",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
                "executable": "openclaw",
            }
            with self.assertRaises(FileNotFoundError):
                install(source, host=host, register_plugin=True)
            self.assertFalse((root / "tools").exists())
            self.assertFalse((root / "skills").exists())
            self.assertFalse((root / "state").exists())

    def test_register_plugin_rejects_non_openclaw_before_mutation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src" / "SKILL.md").write_text("skill", encoding="utf-8")
            host = {
                "name": "codex",
                "tools_dir": str(root / "tools"),
                "skills_dir": str(root / "skills"),
                "state_dir": str(root / "state"),
            }
            with self.assertRaises(ValueError):
                install(source, host=host, register_plugin=True)
            self.assertFalse((root / "tools").exists())
            self.assertFalse((root / "skills").exists())

    def test_windows_cmd_plugin_registration_uses_comspec(self):
        plugin_dir = Path(r"C:\\tmp\\plugin")
        with patch("installer.installer.sys.platform", "win32"), patch.dict(
            os.environ, {"COMSPEC": r"C:\\Windows\\System32\\cmd.exe"}, clear=False
        ):
            command = _openclaw_plugin_command(r"C:\\npm\\openclaw.cmd", plugin_dir)
        self.assertEqual(
            command[:4],
            (r"C:\\Windows\\System32\\cmd.exe", "/d", "/s", "/c"),
        )
        self.assertIn("openclaw.cmd", command[4])
        self.assertIn("plugins install", command[4])


if __name__ == "__main__":
    unittest.main()
