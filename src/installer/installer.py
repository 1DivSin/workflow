from __future__ import annotations

import json
import math
import os
import re
import sys
import shutil
import subprocess
import tomllib
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"

_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def _toml_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _toml_value(value: object) -> str:
    """Serialize one tomllib value for the narrow inline-table rewrite below."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{_toml_key(str(key))} = {_toml_value(item)}"
            for key, item in value.items()
        )
        return "{ " + entries + " }"
    raise TypeError(f"Unsupported TOML value in mcp_servers: {type(value).__name__}")


def _expand_inline_codex_mcp_table(
    lines: list[str], servers: dict[str, object]
) -> list[str]:
    """Turn root ``mcp_servers = {...}`` into an extendable TOML table.

    TOML inline tables are sealed, so appending ``[mcp_servers.fusion_flow]``
    after one is invalid even when ``fusion_flow`` is not present.  Rewriting
    only this root assignment to a normal table preserves the parsed user-owned
    entries while allowing the managed server block to be appended and updated.
    """
    candidates = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^\s*mcp_servers\s*=\s*\{", line)
    ]
    if not candidates:
        return lines
    if len(candidates) != 1:
        raise ValueError("Ambiguous inline mcp_servers assignment")
    index = candidates[0]
    replacement = ["[mcp_servers]"]
    replacement.extend(
        f"{_toml_key(str(name))} = {_toml_value(server)}"
        for name, server in servers.items()
    )
    lines[index : index + 1] = replacement
    return lines


def configure_codex_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Register the workflow MCP server in Codex config idempotently."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    config_data = tomllib.loads(text)
    lines = text.splitlines()
    if _CODEX_BEGIN in lines or _CODEX_END in lines:
        if lines.count(_CODEX_BEGIN) != 1 or lines.count(_CODEX_END) != 1:
            raise ValueError("Incomplete or duplicate dynamic-workflow config markers")
        start = lines.index(_CODEX_BEGIN)
        end = lines.index(_CODEX_END, start)
    else:
        servers = config_data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise ValueError("mcp_servers must be a TOML table")
        if "fusion_flow" in servers:
            return path  # An existing user-owned server is authoritative.
        lines = _expand_inline_codex_mcp_table(lines, servers)
        if lines and lines[-1].strip():
            lines.append("")
        start, end = len(lines), len(lines) - 1

    lines[start : end + 1] = (
        [
            _CODEX_BEGIN,
            "[mcp_servers.fusion_flow]",
            f"command = {json.dumps(sys.executable)}",
            'args = ["-m", "fusion_flow.mcp_server"]',
            "[mcp_servers.fusion_flow.env]",
            f"PYTHONPATH = {json.dumps(str(Path(runtime).resolve() / 'src'))}",
            'PSI_WORKFLOW_HOST = "codex"',
            f"PSI_WORKFLOW_WORKSPACE = {json.dumps(str(Path(workspace).resolve()))}",
            _CODEX_END,
        ]
    )

    result = "\n".join(lines).rstrip() + "\n"
    tomllib.loads(result)
    path.write_text(result, encoding="utf-8")
    return path


def _has_hermes_server(lines: list[str]) -> bool:
    try:
        start = next(
            i
            for i, line in enumerate(lines)
            if re.fullmatch(r"mcp_servers:\s*", line)
        )
    except StopIteration:
        return False

    return any(
        re.fullmatch(r"  fusion_flow:\s*", line)
        for line in lines[start + 1 :]
    )


def configure_hermes_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Add the workflow MCP server without overwriting user configuration."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    try:
        start = lines.index(_HERMES_BEGIN)
        end = lines.index(_HERMES_END, start)
        del lines[start : end + 1]
    except ValueError:
        if _has_hermes_server(lines):
            return path

    if not any(re.fullmatch(r"mcp_servers:\s*", line) for line in lines):
        lines.append("mcp_servers:")

    if lines and lines[-1].strip():
        lines.append("")

    lines.extend(
        [
            _HERMES_BEGIN,
            "  fusion_flow:",
            f"    command: {json.dumps(sys.executable)}",
            '    args: ["-m", "fusion_flow.mcp_server"]',
            "    env:",
            f"      PYTHONPATH: {json.dumps(str(Path(runtime).resolve() / 'src'))}",
            '      PSI_WORKFLOW_HOST: "hermes"',
            f"      PSI_WORKFLOW_WORKSPACE: {json.dumps(str(Path(workspace).resolve()))}",
            _HERMES_END,
        ]
    )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def install(
    source,
    host=None,
    destination=None,
    *,
    register_plugin: bool = False,
    runner: Callable[..., object] = subprocess.run,
):
    h = host or detect_host()
    s = Path(source).resolve()
    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method")

    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)

    shutil.copytree(
        s,
        d,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".git",
            "*.egg-info",
        ),
    )

    skill_dir = Path(h["skills_dir"]) / "workflow"
    skill_source = d / "src" / "SKILL.md"
    if skill_source.is_file():
        skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_source, skill_dir / "SKILL.md")

    if h["name"] == "codex":
        home = Path(h.get("home", Path(h["state_dir"]).parent))
        configure_codex_mcp(
            Path(os.getenv("CODEX_CONFIG", str(home / "config.toml"))),
            d,
            h.get("workspace", "."),
        )

    if h["name"] == "hermes":
        configure_hermes_mcp(
            Path(h["home"]) / "config.yaml",
            d,
            h["workspace"],
        )
        Path(h["state_dir"]).mkdir(parents=True, exist_ok=True)
        (
            Path(h["state_dir"]) / "genuineknowledge-method.json"
        ).write_text(
            json.dumps(
                {
                    "target": str(d),
                    "skill_dir": str(Path(h["skills_dir"]) / "workflow"),
                    "host": h["name"],
                },
                indent=2,
            )
        )
        return d

    plugin_dir = d / "plugins" / "openclaw-workflow"
    registered = False

    if register_plugin:
        if h.get("name") != "openclaw":
            raise ValueError(
                "--register-plugin is only supported for OpenClaw"
            )

        if not (plugin_dir / "openclaw.plugin.json").is_file():
            raise FileNotFoundError(
                f"OpenClaw plugin manifest is missing: {plugin_dir}"
            )

        executable = h.get("executable") or shutil.which("openclaw")
        if not executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to register the plugin"
            )

        command: Sequence[str] = (
            str(executable),
            "plugins",
            "install",
            "--link",
            str(plugin_dir),
            "--force",
        )
        runner(command, check=True)
        registered = True

    state_dir = Path(h["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "target": str(d),
        "skill_dir": str(skill_dir),
        "host": h["name"],
    }

    if plugin_dir.is_dir():
        state["plugin_dir"] = str(plugin_dir)
        state["plugin_registered"] = registered

    (state_dir / "genuineknowledge-method.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    return d
