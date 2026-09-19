import argparse
import json
import os
from pathlib import Path

from .detect import HOSTS, detect_host, detect_hosts
from .doctor import diagnose
from .installer import install, install_many
from .uninstaller import uninstall


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dynamic-workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    detect = subparsers.add_parser("detect")
    installer = subparsers.add_parser("install", aliases=["installer"])
    installer.add_argument("source", nargs="?", default=None)
    installer.add_argument("--destination")
    installer.add_argument("--register-plugin", action="store_true")
    installer.add_argument("--accept-capabilities", action="store_true")
    installer.add_argument("--workspace", type=Path, default=Path.cwd())
    selection = installer.add_mutually_exclusive_group()
    selection.add_argument("--host", action="append", choices=HOSTS,
                           help="Select a host; repeat to install multiple hosts")
    selection.add_argument("--all", action="store_true", help="Install every detected host")
    uninstaller = subparsers.add_parser("uninstall", aliases=["uninstaller"])
    uninstaller.add_argument("--target")
    uninstaller.add_argument("--purge-state", action="store_true")
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--root", default=".")
    for command in (detect, uninstaller, doctor):
        command.add_argument("--host", choices=HOSTS)
        command.add_argument("--workspace", type=Path, default=Path.cwd())

    args = parser.parse_args(argv)
    is_install = args.command in {"install", "installer"}
    requested = list(dict.fromkeys(args.host or [])) if is_install else []
    if is_install and args.register_plugin:
        if requested and requested != ["openclaw"]:
            parser.error("--register-plugin requires --host openclaw")
        requested = ["openclaw"]

    if is_install and args.all:
        hosts = detect_hosts(getattr(args, "workspace", Path.cwd()), environ=dict(os.environ))
        if not hosts:
            parser.error("No supported workflow host detected")
        if args.destination:
            parser.error("--destination cannot be used with --all")
        results = install_many(
            args.source,
            hosts,
            register_plugin=True,
            accept_capabilities=args.accept_capabilities,
        )
        for result in results:
            if result["ok"]:
                print(f"{result['host']}: OK runtime={result['target']}")
            else:
                print(f"{result['host']}: FAILED {result['error']}")
        return 0 if all(result["ok"] for result in results) else 1

    if is_install and len(requested) > 1:
        hosts = [detect_host(getattr(args, "workspace", Path.cwd()), target=name, environ=dict(os.environ)) for name in requested]
        if args.destination:
            parser.error("--destination cannot be used with multiple hosts")
        results = install_many(
            args.source,
            hosts,
            register_plugin=args.register_plugin,
            accept_capabilities=args.accept_capabilities,
        )
        for result in results:
            if result["ok"]:
                print(f"{result['host']}: OK runtime={result['target']}")
            else:
                print(f"{result['host']}: FAILED {result['error']}")
        return 0 if all(result["ok"] for result in results) else 1

    selected_host = requested[0] if requested else (args.host if not is_install else None)
    environment = dict(os.environ)
    if selected_host:
        environment["PSI_WORKFLOW_HOST"] = selected_host
    host = detect_host(getattr(args, "workspace", Path.cwd()), target=selected_host, environ=environment)
    host["workspace"] = str(getattr(args, "workspace", Path.cwd()).resolve())

    if is_install:
        install_host = host if host["available"] and (not selected_host or host["name"] == selected_host) else None
        print("installed integration to", install(
            args.source,
            host=install_host,
            destination=args.destination,
            target_host=selected_host,
            register_plugin=args.register_plugin,
            accept_capabilities=args.accept_capabilities,
        ))
        return 0

    if selected_host and (host["name"] != selected_host or not host["available"]):
        parser.error(f"{selected_host} is not installed; install the host or configure its HOME/executable first")
    if args.command == "detect":
        print(json.dumps(host, indent=2))
    elif args.command in {"uninstall", "uninstaller"}:
        for path in uninstall(host=host, target=args.target, purge_state=args.purge_state):
            print("removed", path)
    else:
        report = diagnose(args.root, host=host)
        print(json.dumps(report, indent=2))
        if not report["ok"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
