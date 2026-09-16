from __future__ import annotations

import argparse
import json

from .detect import detect_host
from .installer import install
from .uninstaller import uninstall
from .doctor import diagnose


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dynamic-workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect")
    installer = sub.add_parser("installer")
    installer.add_argument("source", nargs="?", default=".")
    installer.add_argument("--destination")
    installer.add_argument("--yes", action="store_true", help="skip confirmation")
    uninstaller = sub.add_parser("uninstaller")
    uninstaller.add_argument("--target")
    uninstaller.add_argument("--purge-state", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    if args.command == "detect":
        print(json.dumps(detect_host(), indent=2))
    elif args.command == "installer":
        host = detect_host(args.source)
        if not host["available"]:
            parser.error("No supported workflow host detected")
        if not args.yes and input(f"Install workflow for {host['name']}? [y/N]: ").strip().lower() not in {"y", "yes"}:
            print("CANCELLED")
            return 1
        print(f"SUCCESS: installed to {install(args.source, host=host, destination=args.destination)}")
    elif args.command == "uninstaller":
        for path in uninstall(target=args.target, purge_state=args.purge_state):
            print("removed", path)
    else:
        print(json.dumps(diagnose(args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
