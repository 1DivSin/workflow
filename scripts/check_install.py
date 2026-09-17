"""Install the packaged runtime and exercise its host integration in isolation.

No model credentials are needed. This verifies that a `uv tool install` deployment
can register the integration and launch the MCP server without depending on the
source checkout's Python interpreter or PYTHONPATH.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _tool_entrypoint(bin_dir: Path, name: str) -> Path:
    candidates = [bin_dir / name]
    if os.name == "nt":
        candidates = [bin_dir / f"{name}.exe", bin_dir / f"{name}.cmd", *candidates]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} was not installed under {bin_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=["codex", "hermes", "openclaw"], required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required for the installation smoke test")

    with tempfile.TemporaryDirectory(prefix="workflow-install-") as raw:
        area = Path(raw)
        home, project = area / "home", area / "project"
        tool_dir, bin_dir = area / "uv-tools", area / "bin"
        project.mkdir()
        bin_dir.mkdir()
        (home / ("." + args.host)).mkdir(parents=True)
        for child in ("tmp", "cache", "local", "appdata"):
            (area / child).mkdir()

        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                (
                    "CODEX_",
                    "HERMES_",
                    "OPENCLAW_",
                    "PSI_WORKFLOW_",
                    "DYNAMIC_WORKFLOW_",
                    "UV_TOOL_",
                )
            )
        }
        env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            PYTHONIOENCODING="utf-8",
            PYTHONDONTWRITEBYTECODE="1",
            OPENCLAW_STATE_DIR=str(home / ".openclaw"),
            OPENCLAW_CONFIG_PATH=str(home / ".openclaw" / "openclaw.json"),
            UV_TOOL_DIR=str(tool_dir),
            UV_TOOL_BIN_DIR=str(bin_dir),
            PATH=str(bin_dir) + os.pathsep + env.get("PATH", ""),
        )
        env.update(
            TEMP=str(area / "tmp"),
            TMP=str(area / "tmp"),
            TMPDIR=str(area / "tmp"),
            XDG_CACHE_HOME=str(area / "cache"),
            LOCALAPPDATA=str(area / "local"),
            APPDATA=str(area / "appdata"),
        )

        subprocess.run(
            [uv, "tool", "install", "--force", "--python", "3.12", str(ROOT)],
            env=env,
            check=True,
            cwd=ROOT,
            timeout=300,
        )
        cli = _tool_entrypoint(bin_dir, "dynamic-workflow")

        command = [
            str(cli),
            "install",
            "--host",
            args.host,
            "--workspace",
            str(project),
        ]
        if args.host == "openclaw":
            command += ["--register-plugin", "--accept-capabilities"]
        subprocess.run(command, env=env, check=True, cwd=project, timeout=240)

        state = json.loads(
            (home / ("." + args.host) / "state" / "genuineknowledge-method.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["runtime_mode"] == "installed", state
        assert state["mcp_command"][0].startswith(str(bin_dir)), state
        assert str(ROOT) not in state["mcp_command"][0], state

        doctor = subprocess.run(
            [
                str(cli),
                "doctor",
                "--host",
                args.host,
                "--workspace",
                str(project),
            ],
            env=env,
            cwd=project,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
        )
        print(doctor.stdout)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(doctor.stdout, encoding="utf-8")
        if doctor.returncode:
            raise RuntimeError(doctor.stderr or doctor.stdout)
        report = json.loads(doctor.stdout)
        assert report["ok"] and report["checks"]["tool_call"], report


if __name__ == "__main__":
    main()
