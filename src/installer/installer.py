from __future__ import annotations

import json
import os
import re
import sys
import shutil
import subprocess
import yaml
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"

_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def configure_codex_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Register the workflow MCP server in Codex config idempotently."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    try:
        start = lines.index(_CODEX_BEGIN)
        end = lines.index(_CODEX_END, start)
        del lines[start : end + 1]
    except ValueError:
        pass

    if lines and lines[-1].strip():
        lines.append("")

    lines.extend(
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

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def configure_hermes_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Add the workflow MCP server without overwriting user configuration."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = yaml.safe_load(text)
    if data is not None and not isinstance(data, dict):
        raise ValueError("Hermes config must be a YAML mapping")
    lines = text.splitlines()
    markers = [line.strip() for line in lines]
    begin, finish = _HERMES_BEGIN.strip(), _HERMES_END.strip()
    if begin in markers or finish in markers:
        if markers.count(begin) != 1 or markers.count(finish) != 1:
            raise ValueError("Incomplete or duplicate dynamic-workflow config markers")
        start = markers.index(begin)
        end = markers.index(finish, start)
        del lines[start : end + 1]
    remaining = "\n".join(lines) + "\n"
    data = yaml.safe_load(remaining) or {}
    servers = data.get("mcp_servers")
    if servers is not None and not isinstance(servers, dict):
        raise ValueError("mcp_servers must be a YAML mapping")
    if isinstance(servers, dict) and "fusion_flow" in servers:
        return path  # Preserve an existing user-owned server, including its comments.

    document = yaml.compose(remaining)
    entries = [] if document is None else [
        (key, value) for key, value in document.value if key.value == "mcp_servers"
    ]
    if len(entries) > 1:
        raise ValueError("Duplicate mcp_servers mappings in Hermes config")
    indent = 2
    if not entries:
        lines.append("mcp_servers:")
        insertion = len(lines)
    else:
        key, value = entries[0]
        if servers:
            if value.flow_style:
                raise ValueError("Use block-style YAML for mcp_servers before adding a server")
            if value.start_mark.line < key.start_mark.line:
                raise ValueError("Define mcp_servers as an in-place mapping instead of a YAML alias")
            first_child = value.value[0][0]
            insertion = first_child.start_mark.line
            indent = first_child.start_mark.column
        else:
            # Turn an empty mapping or null into a block mapping, keeping comments.
            remaining = remaining[:value.start_mark.index] + remaining[value.end_mark.index:]
            lines = remaining.splitlines()
            insertion = key.start_mark.line + 1

    block = [
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
    lines[insertion:insertion] = [" " * indent + line[2:] for line in block]
    result = "\n".join(lines).rstrip() + "\n"
    yaml.safe_load(result)
    path.write_text(result, encoding="utf-8")
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
