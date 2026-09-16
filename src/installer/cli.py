import argparse
import json
import os
from pathlib import Path

from .detect import HOSTS, detect_host
from .doctor import diagnose
from .installer import install
from .uninstaller import uninstall


def main(argv=None):
    parser = argparse.ArgumentParser(prog="method-installer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    detect = subparsers.add_parser("detect")
    installer = subparsers.add_parser("installer")
    installer.add_argument("source", nargs="?", default=".")
    installer.add_argument("--destination")
    installer.add_argument("--register-plugin", action="store_true")
    installer.add_argument("--accept-capabilities", action="store_true", help="Pass OpenClaw capability consent to its native installer")
    uninstaller = subparsers.add_parser("uninstaller")
    uninstaller.add_argument("--target")
    uninstaller.add_argument("--purge-state", action="store_true")
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--root", default=".")
    for command in (detect, installer, uninstaller, doctor):
        command.add_argument("--host", choices=HOSTS)
        command.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    environment = dict(os.environ)
    if args.host:
        environment["PSI_WORKFLOW_HOST"] = args.host
    host = detect_host(args.workspace, environ=environment)
    if args.host and (host["name"] != args.host or not host["available"]):
        parser.error(f"{args.host} is not installed; install the host or configure its HOME/executable first")
    host["workspace"] = str(args.workspace.resolve())
    if args.command == "detect":
        print(json.dumps(host, indent=2))
    elif args.command == "installer":
        print("installed to", install(args.source, host=host, destination=args.destination, register_plugin=args.register_plugin, accept_capabilities=args.accept_capabilities))
    elif args.command == "uninstaller":
        for path in uninstall(host=host, target=args.target, purge_state=args.purge_state):
            print("removed", path)
    else:
        report = diagnose(args.root, host=host)
        print(json.dumps(report, indent=2))
        if not report["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
