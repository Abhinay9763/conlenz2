from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget


def resolve_app_icon() -> QIcon:
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


def apply_window_icon(window: QWidget) -> None:
    icon = resolve_app_icon()
    if not icon.isNull():
        window.setWindowIcon(icon)
