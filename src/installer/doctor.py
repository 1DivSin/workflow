"""Read back an installed integration and exercise its MCP process."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .detect import detect_host
from .installer import _openclaw_cli_command

TOOLS = {"run_flow", "run_flow_resume", "flow_manage"}


def _command_available(command: str) -> bool:
    path = Path(command).expanduser()
    if path.is_absolute() or path.parent != Path("."):
        return path.is_file()
    return shutil.which(command) is not None


def diagnose(root=".", *, host=None):
    h = host or detect_host(root)
    checks = {}
    try:
        if sys.version_info < (3, 12):
            raise RuntimeError("Python 3.12 or newer is required")
        state = json.loads(
            (Path(h["state_dir"]) / "genuineknowledge-method.json").read_text(encoding="utf-8")
        )
        target, skill = Path(state["target"]), Path(state["skill_dir"])
        checks["skill"] = (
            (skill / "SKILL.md").is_file()
            and (skill / "grammar" / "FusionFlow.g4").is_file()
        )
        checks["assets"] = target.is_dir() and (target / "src" / "SKILL.md").is_file()
        if not all(checks.values()):
            raise RuntimeError("Installed skill resources are missing")

        if h["name"] == "codex":
            config = Path(os.getenv("CODEX_CONFIG", str(Path(h["home"]) / "config.toml")))
            server = tomllib.loads(config.read_text(encoding="utf-8"))["mcp_servers"]["fusion_flow"]
        elif h["name"] == "hermes":
            import yaml

            server = yaml.safe_load(
                (Path(h["home"]) / "config.yaml").read_text(encoding="utf-8")
            )["mcp_servers"]["fusion_flow"]
        else:
            settings = json.loads(
                (target / "plugins" / "openclaw-workflow" / "runtime.json").read_text(
                    encoding="utf-8"
                )
            )
            if settings.get("mcpCommand"):
                command = settings["mcpCommand"]
                server = {
                    "command": command[0],
                    "args": command[1:],
                    "env": {
                        "PSI_WORKFLOW_HOST": "openclaw",
                        "PSI_WORKFLOW_WORKSPACE": settings["workspace"],
                    },
                }
            else:
                server = {
                    "command": settings["python"],
                    "args": ["-m", "fusion_flow.mcp_server"],
                    "env": {
                        "PYTHONPATH": str(Path(settings["runtimeRoot"]) / "src"),
                        "PSI_WORKFLOW_HOST": "openclaw",
                        "PSI_WORKFLOW_WORKSPACE": settings["workspace"],
                    },
                }

            checks["plugin_registered"] = state.get("plugin_registered") is True
            if not checks["plugin_registered"]:
                raise RuntimeError(
                    "OpenClaw plugin has not been registered; install with --register-plugin"
                )
            executable = h.get("executable")
            if not executable:
                raise RuntimeError("OpenClaw management executable is unavailable")
            inspected = subprocess.run(
                _openclaw_cli_command(
                    executable,
                    "plugins",
                    "inspect",
                    "genuineknowledge-workflow",
                    "--runtime",
                    "--json",
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
                timeout=90,
            )
            plugin = json.loads(inspected.stdout)["plugin"]
            checks["plugin_loaded"] = (
                plugin["status"] == "loaded" and set(plugin["toolNames"]) == TOOLS
            )
            if not checks["plugin_loaded"]:
                raise RuntimeError("Native OpenClaw did not load all workflow tools")

        checks["runtime"] = _command_available(server["command"])
        if not checks["runtime"]:
            raise RuntimeError(f"Workflow runtime command is unavailable: {server['command']}")

        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "workflow-doctor", "version": "0.1.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "flow_manage", "arguments": {"action": "list"}},
            },
        ]
        result = subprocess.run(
            [server["command"], *server.get("args", [])],
            input="".join(json.dumps(item) + "\n" for item in requests),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=60,
            cwd=h["workspace"],
            env={
                **os.environ,
                **server.get("env", {}),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        replies = {item["id"]: item for item in map(json.loads, result.stdout.splitlines())}
        checks["mcp_initialize"] = "serverInfo" in replies[1].get("result", {})
        checks["tools"] = {t["name"] for t in replies[2]["result"]["tools"]} == TOOLS
        call = replies[3].get("result", {})
        checks["tool_call"] = bool(call.get("content")) and not call.get("isError", False)
        return {"ok": all(checks.values()), "host": h["name"], "checks": checks}
    except Exception as error:
        return {
            "ok": False,
            "host": h["name"],
            "checks": checks,
            "error": f"{type(error).__name__}: {error}",
        }
