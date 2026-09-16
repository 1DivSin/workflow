import shutil
import sys

from .detect import detect_host


def diagnose(root: str = ".") -> dict[str, object]:
    return {"ok": sys.version_info >= (3, 11) and bool(shutil.which("node")), "host": detect_host(root)}
