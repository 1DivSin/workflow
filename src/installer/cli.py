import argparse
import json

from .detect import HOSTS, detect_host
from .doctor import diagnose
from .installer import install
from .uninstaller import uninstall


def main():
    parser = argparse.ArgumentParser(prog="method-installer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("detect")
    installer = subparsers.add_parser("installer")
    installer.add_argument("source", nargs="?", default=".")
    installer.add_argument("--destination")
    installer.add_argument("--host", choices=HOSTS)
    installer.add_argument("--register-plugin", action="store_true")
    uninstaller = subparsers.add_parser("uninstaller")
    uninstaller.add_argument("--target")
    uninstaller.add_argument("--purge-state", action="store_true")
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--root", default=".")
    args = parser.parse_args()
    if args.command == "detect":
        print(json.dumps(detect_host(), indent=2))
    elif args.command == "installer":
        target_host = args.host
        if args.register_plugin:
            if target_host not in (None, "openclaw"):
                parser.error("--register-plugin requires --host openclaw")
            target_host = "openclaw"
        print(
            "installed to",
            install(
                args.source,
                destination=args.destination,
                target_host=target_host,
                register_plugin=args.register_plugin,
            ),
        )
    elif args.command == "uninstaller":
        for path in uninstall(target=args.target, purge_state=args.purge_state):
            print("removed", path)
    else:
        print(json.dumps(diagnose(args.root), indent=2))


if __name__ == "__main__":
    main()
