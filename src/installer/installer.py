from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path
from typing import Callable, Sequence

import yaml

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


def _normalize_command(command: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(str(part) for part in command)
    if not normalized or not normalized[0]:
        raise ValueError("Runtime command must contain an executable")
    return normalized


def _server_spec(
    command: Sequence[str],
    workspace: str | Path,
    host: str,
) -> dict[str, object]:
    runtime = _normalize_command(command)
    return {
        "command": runtime[0],
        "args": list(runtime[1:]),
        "env": {
            "PSI_WORKFLOW_HOST": host,
            "PSI_WORKFLOW_WORKSPACE": str(Path(workspace).resolve()),
        },
    }


def _reject_host_mismatch(servers: object, target: str) -> None:
    if not isinstance(servers, dict):
        return
    server = servers.get("fusion_flow")
    if not isinstance(server, dict):
        return
    env = server.get("env")
    configured = env.get("PSI_WORKFLOW_HOST") if isinstance(env, dict) else None
    if isinstance(configured, str) and configured.strip().lower() not in {"", target}:
        raise ValueError(
            f"Existing fusion_flow server is configured for host {configured!r}, "
            f"cannot install it for host {target!r}"
        )


def _codex_server_spec(
    command: Sequence[str],
    workspace: str | Path,
) -> dict[str, object]:
    return _server_spec(command, workspace, "codex")


def _inline_mcp_servers_line(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if re.match(r"^\s*mcp_servers\s*=\s*\{", line):
            return index
    return None


def configure_codex_mcp(
    config: str | Path,
    mcp_command: Sequence[str],
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
            _reject_host_mismatch(servers, "codex")
            return path

        if inline_index is not None:
            updated_servers = dict(servers)
            updated_servers["fusion_flow"] = _codex_server_spec(mcp_command, workspace)
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

    server = _codex_server_spec(mcp_command, workspace)
    lines[start : end + 1] = [
        _CODEX_BEGIN,
        "[mcp_servers.fusion_flow]",
        f"command = {json.dumps(server['command'])}",
        f"args = {_toml_inline_value(server['args'])}",
        "[mcp_servers.fusion_flow.env]",
        'PSI_WORKFLOW_HOST = "codex"',
        f"PSI_WORKFLOW_WORKSPACE = {json.dumps(server['env']['PSI_WORKFLOW_WORKSPACE'])}",
        _CODEX_END,
    ]

    result = "\n".join(lines).rstrip() + "\n"
    tomllib.loads(result)
    path.write_text(result, encoding="utf-8")
    return path


def configure_hermes_mcp(
    config: str | Path,
    mcp_command: Sequence[str],
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
        _reject_host_mismatch(servers, "hermes")
        return path

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
            remaining = remaining[:value.start_mark.index] + remaining[value.end_mark.index:]
            lines = remaining.splitlines()
            insertion = key.start_mark.line + 1

    server = _server_spec(mcp_command, workspace, "hermes")
    block = [
        _HERMES_BEGIN,
        "  fusion_flow:",
        f"    command: {json.dumps(server['command'])}",
        f"    args: {json.dumps(server['args'])}",
        "    env:",
        '      PSI_WORKFLOW_HOST: "hermes"',
        f"      PSI_WORKFLOW_WORKSPACE: {json.dumps(server['env']['PSI_WORKFLOW_WORKSPACE'])}",
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
    return _openclaw_cli_command(
        executable,
        "plugins",
        "install",
        "--link",
        str(plugin_dir),
        "--force",
    )


def _installed_assets_root() -> Path:
    return Path(sysconfig.get_path("data")) / "share" / "dynamic-workflow"


def _asset_layout(source: str | Path | None) -> dict[str, Path]:
    if source is not None:
        root = Path(source).resolve()
        layout = {
            "skill": root / "src" / "SKILL.md",
            "grammar": root / "src" / "grammar",
            "examples": root / "examples",
            "plugin": root / "plugins" / "openclaw-workflow",
        }
    else:
        root = _installed_assets_root()
        layout = {
            "skill": root / "SKILL.md",
            "grammar": root / "grammar",
            "examples": root / "examples",
            "plugin": root / "openclaw-workflow",
        }
    if not layout["skill"].is_file():
        mode = f"source tree {root}" if source is not None else f"installed package data {root}"
        raise FileNotFoundError(f"Workflow {mode} has no SKILL.md")
    return layout


def _copy_runtime_assets(layout: dict[str, Path], destination: Path) -> None:
    (destination / "src").mkdir(parents=True, exist_ok=True)
    shutil.copy2(layout["skill"], destination / "src" / "SKILL.md")
    if layout["grammar"].is_dir():
        shutil.copytree(layout["grammar"], destination / "src" / "grammar", dirs_exist_ok=True)
    if layout["examples"].is_dir():
        shutil.copytree(layout["examples"], destination / "examples", dirs_exist_ok=True)
    if layout["plugin"].is_dir():
        shutil.copytree(
            layout["plugin"],
            destination / "plugins" / "openclaw-workflow",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("bridge.test.mjs", "runtime.json"),
        )


def _entrypoint_path(name: str) -> str:
    found = shutil.which(name)
    if found:
        return str(Path(found).absolute())

    current = Path(sys.argv[0]).expanduser()
    if current.exists():
        suffixes = [current.suffix] if current.suffix else [""]
        if os.name == "nt":
            suffixes.extend(
                suffix for suffix in (".exe", ".cmd", ".bat") if suffix not in suffixes
            )
        for suffix in suffixes:
            sibling = current.absolute().with_name(name + suffix)
            if sibling.is_file():
                return str(sibling)
    raise FileNotFoundError(
        f"{name} is not installed. Install the runtime with "
        "`uv tool install git+https://github.com/1DivSin/workflow.git`."
    )


def _resolve_runtime_commands(
    source: str | Path | None,
    *,
    mcp_command: Sequence[str] | None = None,
    tool_command: Sequence[str] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Resolve installed CLI entrypoints or an explicit uv-backed source runtime."""
    if source is None:
        mcp = (
            _normalize_command(mcp_command)
            if mcp_command
            else (_entrypoint_path("dynamic-workflow-mcp"),)
        )
        tool = (
            _normalize_command(tool_command)
            if tool_command
            else (_entrypoint_path("dynamic-workflow-tool"),)
        )
        return mcp, tool, "installed"

    project = Path(source).resolve()
    if mcp_command is not None and tool_command is not None:
        return _normalize_command(mcp_command), _normalize_command(tool_command), "source"

    uv = shutil.which("uv")
    if not uv:
        raise FileNotFoundError(
            "uv is required for source-runtime installation; install with `uv tool install` "
            "for a source-independent runtime"
        )
    mcp = (
        _normalize_command(mcp_command)
        if mcp_command
        else (str(Path(uv).resolve()), "run", "--project", str(project), "dynamic-workflow-mcp")
    )
    tool = (
        _normalize_command(tool_command)
        if tool_command
        else (str(Path(uv).resolve()), "run", "--project", str(project), "dynamic-workflow-tool")
    )
    return mcp, tool, "source"


def install(
    source=None,
    host=None,
    destination=None,
    *,
    target_host: str | None = None,
    register_plugin: bool = False,
    accept_capabilities: bool = False,
    mcp_command: Sequence[str] | None = None,
    tool_command: Sequence[str] | None = None,
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

    layout = _asset_layout(source)
    source_root = Path(source).resolve() if source is not None else None
    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method").resolve()
    if source_root is not None and (
        d == source_root or d in source_root.parents or source_root in d.parents
    ):
        raise ValueError("Runtime destination must be separate from the source tree")

    if register_plugin and h.get("name") != "openclaw":
        raise ValueError("--register-plugin is only supported for OpenClaw")
    if register_plugin and not (layout["plugin"] / "openclaw.plugin.json").is_file():
        raise FileNotFoundError(
            f"OpenClaw plugin manifest is missing: {layout['plugin'] / 'openclaw.plugin.json'}"
        )

    plugin_executable: str | Path | None = None
    if register_plugin:
        plugin_executable = (
            h.get("executable")
            or os.getenv("OPENCLAW_EXECUTABLE")
            or shutil.which("openclaw")
        )
        if not plugin_executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to register the plugin; set "
                "OPENCLAW_EXECUTABLE when OPENCLAW_COMMAND uses a wrapper"
            )

    resolved_mcp, resolved_tool, runtime_mode = _resolve_runtime_commands(
        source_root,
        mcp_command=mcp_command,
        tool_command=tool_command,
    )

    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)
    _copy_runtime_assets(layout, d)

    skill_dir = Path(h["skills_dir"]) / "workflow"
    skill_source = d / "src" / "SKILL.md"
    skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_source, skill_dir / "SKILL.md")
    for resource, source_resource in (
        ("grammar", d / "src" / "grammar"),
        ("examples", d / "examples"),
    ):
        if source_resource.is_dir():
            shutil.copytree(source_resource, skill_dir / resource, dirs_exist_ok=True)

    if h["name"] == "codex":
        home = Path(h.get("home", Path(h["state_dir"]).parent))
        configure_codex_mcp(
            Path(os.getenv("CODEX_CONFIG", str(home / "config.toml"))),
            resolved_mcp,
            h.get("workspace", "."),
        )

    if h["name"] == "hermes":
        configure_hermes_mcp(
            Path(h["home"]) / "config.yaml",
            resolved_mcp,
            h["workspace"],
        )

    plugin_dir = d / "plugins" / "openclaw-workflow"
    registered = False
    if h.get("name") == "openclaw" and plugin_dir.is_dir():
        (plugin_dir / "runtime.json").write_text(
            json.dumps(
                {
                    "mcpCommand": list(resolved_mcp),
                    "toolCommand": list(resolved_tool),
                    "workspace": str(Path(h.get("workspace", ".")).resolve()),
                },
                indent=2,
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
        "runtime_mode": runtime_mode,
        "mcp_command": list(resolved_mcp),
        "tool_command": list(resolved_tool),
    }
    if source_root is not None:
        state["source"] = str(source_root)
    if plugin_dir.is_dir():
        state["plugin_dir"] = str(plugin_dir)
        state["plugin_registered"] = registered

    (state_dir / "genuineknowledge-method.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    return d


def install_many(
    source=None,
    hosts=(),
    *,
    destination=None,
    register_plugin=False,
    accept_capabilities=False,
) -> list[dict[str, object]]:
    """Install each selected host and collect failures so later hosts still run."""
    hosts = list(hosts)
    if destination is not None and len(hosts) > 1:
        raise ValueError("--destination can only be used with one host")
    results = []
    for host in hosts:
        name = str(host["name"])
        result = {"host": name}
        try:
            target = install(
                source, host=host, destination=destination, target_host=name,
                register_plugin=register_plugin and name == "openclaw",
                accept_capabilities=accept_capabilities,
            )
        except Exception as error:
            result.update(ok=False, error=str(error))
        else:
            result.update(ok=True, target=str(target))
        results.append(result)
    return results
