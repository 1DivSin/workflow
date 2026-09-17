import argparse
import json
import os
from pathlib import Path

from .detect import HOSTS, detect_host
from .doctor import diagnose
from .installer import install
from .uninstaller import uninstall


def _installation_summary(host: dict, target: Path, *, register_plugin: bool) -> list[str]:
    """Describe the concrete host integration changes made by a successful install."""
    target = Path(target)
    skill_dir = Path(host["skills_dir"]) / "workflow"
    host_name = host.get("name", "generic")

    if host_name == "codex":
        home = Path(host.get("home", Path(host["state_dir"]).parent))
        config = Path(os.getenv("CODEX_CONFIG", str(home / "config.toml")))
        integration = f"Codex MCP configured: {config}"
    elif host_name == "hermes":
        integration = f"Hermes MCP configured: {Path(host['home']) / 'config.yaml'}"
    elif host_name == "openclaw":
        plugin_dir = target / "plugins" / "openclaw-workflow"
        action = "registered and enabled" if register_plugin else "runtime configured"
        integration = f"OpenClaw plugin {action}: {plugin_dir}"
    else:
        integration = f"Host integration configured: {host_name}"

    state_file = Path(host["state_dir"]) / "genuineknowledge-method.json"
    return [
        f"[1/4] Runtime assets installed: {target}",
        f"[2/4] Workflow skill installed: {skill_dir}",
        f"[3/4] {integration}",
        f"[4/4] Installation state written: {state_file}",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dynamic-workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    detect = subparsers.add_parser("detect")
    installer = subparsers.add_parser("install", aliases=["installer"])
    installer.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "Optional source checkout for development mode. "
            "Omit after `uv tool install` to use the installed runtime."
        ),
    )
    installer.add_argument("--destination")
    installer.add_argument("--register-plugin", action="store_true")
    installer.add_argument(
        "--accept-capabilities",
        action="store_true",
        help="Pass OpenClaw capability consent to its native installer",
    )
    uninstaller = subparsers.add_parser("uninstall", aliases=["uninstaller"])
    uninstaller.add_argument("--target")
    uninstaller.add_argument("--purge-state", action="store_true")
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--root", default=".")
    for command in (detect, installer, uninstaller, doctor):
        command.add_argument("--host", choices=HOSTS)
        command.add_argument("--workspace", type=Path, default=Path.cwd())

    args = parser.parse_args(argv)
    selected_host = args.host
    if args.command in {"install", "installer"} and args.register_plugin:
        if selected_host not in (None, "openclaw"):
            parser.error("--register-plugin requires --host openclaw")
        selected_host = "openclaw"

    environment = dict(os.environ)
    if selected_host:
        environment["PSI_WORKFLOW_HOST"] = selected_host
    host = detect_host(args.workspace, target=selected_host, environ=environment)
    host["workspace"] = str(args.workspace.resolve())

    if args.command in {"install", "installer"}:
        install_host = host
        if selected_host and (host["name"] != selected_host or not host["available"]):
            install_host = None
        target = install(
            args.source,
            host=install_host,
            destination=args.destination,
            target_host=selected_host,
            register_plugin=args.register_plugin,
            accept_capabilities=args.accept_capabilities,
        )
        for line in _installation_summary(host, target, register_plugin=args.register_plugin):
            print(line)
        print("Installation complete.")

        command = "uv run dynamic-workflow" if args.source is not None else "dynamic-workflow"
        workspace = json.dumps(str(args.workspace.resolve()))
        host_name = selected_host or host["name"]
        host_arg = f" --host {host_name}" if host_name in HOSTS else ""
        print("Run:")
        print(f"  {command} doctor{host_arg} --workspace {workspace}")
        return

    if selected_host and (host["name"] != selected_host or not host["available"]):
        parser.error(
            f"{selected_host} is not installed; install the host or configure its HOME/executable first"
        )

    if args.command == "detect":
        print(json.dumps(host, indent=2))
    elif args.command in {"uninstall", "uninstaller"}:
        for path in uninstall(host=host, target=args.target, purge_state=args.purge_state):
            print("removed", path)
    else:
        report = diagnose(args.root, host=host)
        print(json.dumps(report, indent=2))
        if not report["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
