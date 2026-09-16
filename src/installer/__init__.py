"""Install the workflow runtime and its host skill."""

from .detect import detect_host
from .installer import install
from .uninstaller import uninstall

__all__ = ["detect_host", "install", "uninstall"]
