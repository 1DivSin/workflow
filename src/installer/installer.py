from __future__ import annotations

import json
import os
import re
import sys
import shutil
import subprocess
import yaml
import tomllib
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"
_CODEX_INLINE_MANAGED = "# dynamic-workflow managed fusion_flow"

_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def _toml_key(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else json.dumps(value)


def _toml_inline_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{_toml_key(str(key))} = {_toml_inline_value(item)}"
            for key, item in value.items()
        ) + " }"
    raise ValueError(f"Unsupported TOML value in inline mcp_servers: {type(value).__name__}")


def _codex_server_spec(runtime: str | Path, workspace: str | Path) -> dict[str, object]:
    return {
        "command": sys.executable,
        "args": ["-m", "fusion_flow.mcp_server"],
        "env": {
            "PYTHONPATH": str(Path(runtime).resolve() / "src"),
            "PSI_WORKFLOW_HOST": "codex",
            "PSI_WORKFLOW_WORKSPACE": str(Path(workspace).resolve()),
        },
    }


def _inline_mcp_servers_line(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if re.match(r"^\s*mcp_servers\s*=\s*\{", line):
            return index
    return None


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

        inline_index = _inline_mcp_servers_line(lines)
        inline_is_managed = (
            inline_index is not None and _CODEX_INLINE_MANAGED in lines[inline_index]
        )
        if "fusion_flow" in servers and not inline_is_managed:
            return path  # An existing user-owned server is authoritative.

        if inline_index is not None:
            updated_servers = dict(servers)
            updated_servers["fusion_flow"] = _codex_server_spec(runtime, workspace)
            lines[inline_index] = (
                f"mcp_servers = {_toml_inline_value(updated_servers)}  {_CODEX_INLINE_MANAGED}"
            )
            result = "\n".join(lines).rstrip() + "\n"
            tomllib.loads(result)
            path.write_text(result, encoding="utf-8")
            return path

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


def _openclaw_cli_command(executable: str | Path, *arguments: str) -> tuple[str, ...]:
    command = (str(executable), *arguments)
    if sys.platform == "win32" and str(executable).lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return (comspec, "/d", "/s", "/c", subprocess.list2cmdline(command))
    return command


def _openclaw_plugin_command(executable: str | Path, plugin_dir: Path) -> tuple[str, ...]:
    """Backward-compatible plugin-install command builder from the main branch."""
    return _openclaw_cli_command(
        executable,
        "plugins",
        "install",
        "--link",
        str(plugin_dir),
        "--force",
    )


def install(
    source,
    host=None,
    destination=None,
    *,
    target_host: str | None = None,
    register_plugin: bool = False,
    accept_capabilities: bool = False,
    runner: Callable[..., object] = subprocess.run,
):
    if register_plugin:
        if target_host not in (None, "openclaw"):
            raise ValueError("--register-plugin requires the OpenClaw host")
        if host is not None and host.get("name") != "openclaw":
            raise ValueError("--register-plugin is only supported for OpenClaw")
        target_host = "openclaw"

    h = host or detect_host(target=target_host)
    if target_host is not None and h.get("name") != target_host:
        raise RuntimeError(f"Requested host {target_host!r} is not available")

    s = Path(source).resolve()
    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method").resolve()
    if d == s or d in s.parents or s in d.parents:
        raise ValueError("Runtime destination must be separate from the source tree")
    if not (s / "src" / "SKILL.md").is_file():
        raise FileNotFoundError(f"Workflow source has no src/SKILL.md: {s}")
    if register_plugin and h.get("name") != "openclaw":
        raise ValueError("--register-plugin is only supported for OpenClaw")

    plugin_executable: str | Path | None = None
    if register_plugin:
        plugin_source = s / "plugins" / "openclaw-workflow"
        if not (plugin_source / "openclaw.plugin.json").is_file():
            raise FileNotFoundError(f"OpenClaw plugin manifest is missing: {plugin_source}")
        plugin_executable = (
            h.get("executable")
            or os.getenv("OPENCLAW_EXECUTABLE")
            or shutil.which("openclaw")
        )
        if not plugin_executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to register the plugin; set OPENCLAW_EXECUTABLE when OPENCLAW_COMMAND uses a wrapper"
            )

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
            ".venv",
            "node_modules",
            ".uv-cache",
            ".uv-python",
            "dist",
            "build",
        ),
    )

    skill_dir = Path(h["skills_dir"]) / "workflow"
    skill_source = d / "src" / "SKILL.md"
    if skill_source.is_file():
        skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_source, skill_dir / "SKILL.md")
        for resource in ("grammar", "examples"):
            source_resource = d / "src" / resource if resource == "grammar" else d / resource
            if source_resource.is_dir():
                shutil.copytree(source_resource, skill_dir / resource, dirs_exist_ok=True)

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
        (Path(h["state_dir"]) / "genuineknowledge-method.json").write_text(
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
    if h.get("name") == "openclaw" and plugin_dir.is_dir():
        (plugin_dir / "runtime.json").write_text(
            json.dumps(
                {
                    "runtimeRoot": str(d),
                    "python": sys.executable,
                    "workspace": str(Path(h.get("workspace", ".")).resolve()),
                }
            ),
            encoding="utf-8",
        )

    if register_plugin:
        assert plugin_executable is not None
        install_args = ["plugins", "install", "--link", str(plugin_dir), "--force"]
        if accept_capabilities:
            install_args.append("--accept-capabilities")
        install_command: Sequence[str] = _openclaw_cli_command(plugin_executable, *install_args)
        runner(install_command, check=True)

        enable_args = ["plugins", "enable", "genuineknowledge-workflow"]
        if accept_capabilities:
            enable_args.append("--accept-capabilities")
        enable_command: Sequence[str] = _openclaw_cli_command(plugin_executable, *enable_args)
        runner(enable_command, check=True)
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
